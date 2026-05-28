"""Segment emission for the transform stage."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from ...common.ids import SeriesId, TextUnitId, VolumeId
from .chapters import ChapterSplit, UnitSlice
from .contracts import Segment, SegmentFile
from .quotes import Token, tokenize

logger = logging.getLogger("ln_voice_over_v2.transform.segments")

_EXCESSIVE_BLANK_LINES = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class _RunSlice:
    text_unit_id: TextUnitId
    text: str
    start_byte: int
    end_byte: int


def build_segment_files(
    splits: tuple[ChapterSplit, ...],
    series: SeriesId,
    volume: VolumeId,
) -> tuple[SegmentFile, ...]:
    """Build deterministic `SegmentFile` artifacts from chapter splits.

    Args:
        splits: Chapter splits produced by the transform chapter detector.
        series: Canonical series identifier for the emitted artifacts.
        volume: Canonical volume identifier for the emitted artifacts.

    Returns:
        One `SegmentFile` per chapter split, preserving input chapter order.
    """
    return tuple(_build_segment_file(split, series, volume) for split in splits)


def _build_segment_file(
    split: ChapterSplit,
    series: SeriesId,
    volume: VolumeId,
) -> SegmentFile:
    segments: list[Segment] = []
    run: list[UnitSlice] = []

    for unit_slice in split.slices:
        if unit_slice.needs_review:
            _emit_run_segments(run, segments)
            run = []
            _append_needs_review_segment(unit_slice, segments)
            continue
        run.append(unit_slice)

    _emit_run_segments(run, segments)

    return SegmentFile(
        series=series,
        volume=volume,
        chapter_id=split.index_entry.chapter_id,
        segments=tuple(segments),
    )


def _append_needs_review_segment(unit_slice: UnitSlice, segments: list[Segment]) -> None:
    logger.warning(
        "transform.segments: emitted needs_review placeholder for %s",
        unit_slice.text_unit_id,
    )
    segments.append(
        _segment(
            text=f"[needs_review:{unit_slice.text_unit_id}]",
            source_unit_ids=(unit_slice.text_unit_id,),
            parser_hints={"quote_candidate": False, "needs_review": True},
            order=len(segments),
        )
    )


def _emit_run_segments(unit_slices: list[UnitSlice], segments: list[Segment]) -> None:
    run_text, run_slices = _build_run(unit_slices)
    if not run_text:
        return

    start_byte = 0
    for token in tokenize(run_text):
        token_end_byte = start_byte + len(token.text.encode("utf-8"))
        _append_token_segment(
            token,
            start_byte=start_byte,
            end_byte=token_end_byte,
            run_slices=run_slices,
            segments=segments,
        )
        start_byte = token_end_byte


def _build_run(unit_slices: list[UnitSlice]) -> tuple[str, tuple[_RunSlice, ...]]:
    parts: list[str] = []
    run_slices: list[_RunSlice] = []
    start_byte = 0

    for unit_slice in unit_slices:
        normalized = _normalize_text(unit_slice.text)
        end_byte = start_byte + len(normalized.encode("utf-8"))
        if normalized:
            run_slices.append(
                _RunSlice(
                    text_unit_id=unit_slice.text_unit_id,
                    text=normalized,
                    start_byte=start_byte,
                    end_byte=end_byte,
                )
            )
            parts.append(normalized)
        start_byte = end_byte

    return "".join(parts), tuple(run_slices)


def _normalize_text(text: str) -> str:
    return _EXCESSIVE_BLANK_LINES.sub("\n\n", unicodedata.normalize("NFC", text))


def _append_token_segment(
    token: Token,
    *,
    start_byte: int,
    end_byte: int,
    run_slices: tuple[_RunSlice, ...],
    segments: list[Segment],
) -> None:
    text = token.text
    source_start_byte = start_byte
    source_end_byte = end_byte

    if token.kind == "narration":
        text, trim_start_bytes, trim_end_bytes = _trim_with_byte_counts(token.text)
        if not text:
            return
        source_start_byte += trim_start_bytes
        source_end_byte -= trim_end_bytes
        parser_hints: dict[str, Any] = {"quote_candidate": False}
    else:
        parser_hints = {
            "quote_candidate": True,
            "quote_style": token.quote_style,
        }

    if token.quote_unmatched:
        parser_hints["quote_unmatched"] = True
        logger.warning("transform.segments: emitted unmatched quote segment")

    segments.append(
        _segment(
            text=text,
            source_unit_ids=_source_unit_ids_for_range(
                run_slices,
                start_byte=source_start_byte,
                end_byte=source_end_byte,
            ),
            parser_hints=parser_hints,
            order=len(segments),
        )
    )


def _trim_with_byte_counts(text: str) -> tuple[str, int, int]:
    trimmed = text.strip()
    leading_len = len(text) - len(text.lstrip())
    trailing_len = len(text) - len(text.rstrip())
    leading_bytes = len(text[:leading_len].encode("utf-8"))
    trailing_bytes = len(text[len(text) - trailing_len :].encode("utf-8")) if trailing_len else 0
    return trimmed, leading_bytes, trailing_bytes


def _source_unit_ids_for_range(
    run_slices: tuple[_RunSlice, ...],
    *,
    start_byte: int,
    end_byte: int,
) -> tuple[TextUnitId, ...]:
    source_unit_ids: list[TextUnitId] = []
    seen: set[TextUnitId] = set()

    for run_slice in run_slices:
        if run_slice.start_byte >= end_byte or run_slice.end_byte <= start_byte:
            continue
        if run_slice.text_unit_id in seen:
            continue
        seen.add(run_slice.text_unit_id)
        source_unit_ids.append(run_slice.text_unit_id)

    return tuple(source_unit_ids)


def _segment(
    *,
    text: str,
    source_unit_ids: tuple[TextUnitId, ...],
    parser_hints: dict[str, Any],
    order: int,
) -> Segment:
    return Segment(
        segment_id=f"seg_{order + 1:06d}",
        order=order,
        text=text,
        source_unit_ids=source_unit_ids,
        parser_hints=parser_hints,
    )
