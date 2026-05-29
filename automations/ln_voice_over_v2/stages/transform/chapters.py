"""Chapter detection for the transform stage."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ...common.ids import SeriesId
from ...common.json_io import load_json_contract
from ...series.contracts import StoryProfile
from ..prepare.contracts import PreparedTextUnit
from .contracts import ChapterIndexEntry

logger = logging.getLogger("ln_voice_over_v2.transform.chapters")

PACKAGED_DEFAULT_STORY_PROFILE = (
    Path(__file__).resolve().parents[2] / "series" / "templates" / "story_profile.default.json"
)
DEFAULT_DISPLAY_NAME = "Chapter 1"
DEFAULT_CHAPTER_ID = "chapter_01"


@dataclass(frozen=True)
class UnitSlice:
    """One `text_unit`'s contribution to a chapter (possibly partial after a mid-page split)."""

    text_unit_id: str
    text: str
    needs_review: bool


@dataclass(frozen=True)
class ChapterSplit:
    """A detected chapter and its per-unit text slices, in volume order."""

    index_entry: ChapterIndexEntry
    slices: tuple[UnitSlice, ...]


@dataclass(frozen=True)
class _HeadingMatch:
    unit_index: int
    line_start: int
    line_text: str
    num: str | None


@dataclass(frozen=True)
class _MatchResult:
    matched: bool
    num: str | None = None


@dataclass(frozen=True)
class _NumberedAnchor:
    match_index: int
    base: int


def resolve_story_profile_path(data_root: Path, series: SeriesId) -> Path:
    """Return the active story-profile path: per-series override or packaged template."""
    override = data_root / series / "config" / "story_profile.json"
    if override.is_file():
        return override
    return PACKAGED_DEFAULT_STORY_PROFILE


def load_story_profile(path: Path) -> StoryProfile:
    """Load a `StoryProfile` from disk using the strict JSON contract loader."""
    return load_json_contract(path, StoryProfile)


def detect_chapters(
    text_units: tuple[PreparedTextUnit, ...],
    story_profile: StoryProfile,
) -> tuple[ChapterSplit, ...]:
    """Detect chapter boundaries and return one `ChapterSplit` per chapter.

    The first detected chapter absorbs all text from unit 0 up to its heading
    line so no characters are silently dropped. Mid-page splits cause one
    `text_unit` to appear in both the prior chapter's tail slice and the new
    chapter's head slice — the per-slice helper captures the partial text.
    """
    if not text_units:
        logger.warning(
            "transform.chapters: text_units is empty; emitting %s fallback",
            DEFAULT_CHAPTER_ID,
        )
        return (_build_fallback_chapter(text_units),)

    patterns = _compile_patterns(story_profile)
    subchapters_enabled = bool(story_profile.rules.get("subchapters", False))
    matches = _collect_matches(text_units, patterns)

    if not matches:
        logger.warning(
            "transform.chapters: no chapter heading matched; emitting single %s",
            DEFAULT_CHAPTER_ID,
        )
        return (_build_fallback_chapter(text_units),)

    return _build_chapter_splits(text_units, matches, patterns, subchapters_enabled)


def _compile_patterns(profile: StoryProfile) -> list[re.Pattern[str]]:
    raw_patterns = profile.rules.get("chapter_headings", [])
    if not isinstance(raw_patterns, list):
        raise ValueError("story_profile.rules.chapter_headings must be a list of regex strings")
    return [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in raw_patterns]


def _collect_matches(
    text_units: tuple[PreparedTextUnit, ...],
    patterns: list[re.Pattern[str]],
) -> list[_HeadingMatch]:
    matches: list[_HeadingMatch] = []
    for unit_index, unit in enumerate(text_units):
        for line_start, line_text in _iter_lines(unit.text):
            result = _try_match(patterns, line_text)
            if not result.matched:
                continue
            matches.append(
                _HeadingMatch(
                    unit_index=unit_index,
                    line_start=line_start,
                    line_text=line_text,
                    num=result.num,
                )
            )
    return matches


def _try_match(patterns: list[re.Pattern[str]], line: str) -> _MatchResult:
    for pattern in patterns:
        match = pattern.search(line)
        if match is None:
            continue
        groupdict = match.groupdict() or {}
        return _MatchResult(matched=True, num=groupdict.get("num"))
    return _MatchResult(matched=False)


def _iter_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield `(line_start_offset, line_text)` for each line in `text`."""
    pos = 0
    n = len(text)
    while pos < n:
        nl = text.find("\n", pos)
        if nl == -1:
            yield pos, text[pos:n]
            return
        yield pos, text[pos:nl]
        pos = nl + 1


def _build_fallback_chapter(
    text_units: tuple[PreparedTextUnit, ...],
) -> ChapterSplit:
    slices = tuple(
        UnitSlice(
            text_unit_id=unit.text_unit_id,
            text=unit.text,
            needs_review=unit.needs_review,
        )
        for unit in text_units
    )
    return ChapterSplit(
        index_entry=ChapterIndexEntry(
            chapter_id=DEFAULT_CHAPTER_ID,
            order=0,
            segments_file=f"segments/{DEFAULT_CHAPTER_ID}.json",
            display_name=DEFAULT_DISPLAY_NAME,
        ),
        slices=slices,
    )


def _build_chapter_splits(
    text_units: tuple[PreparedTextUnit, ...],
    matches: list[_HeadingMatch],
    patterns: list[re.Pattern[str]],
    subchapters_enabled: bool,
) -> tuple[ChapterSplit, ...]:
    chapter_ids = _derive_chapter_ids(matches, subchapters_enabled)
    splits: list[ChapterSplit] = []
    last_unit_index = len(text_units) - 1
    eof_offset = len(text_units[last_unit_index].text)
    order_offset = 0

    if _should_synthesize_front_matter(text_units, matches[0]):
        front_matter_id = "chapter_00"
        splits.append(
            ChapterSplit(
                index_entry=ChapterIndexEntry(
                    chapter_id=front_matter_id,
                    order=0,
                    segments_file=f"segments/{front_matter_id}.json",
                    display_name="Front Matter",
                ),
                slices=_collect_front_matter_slices(text_units, matches[0]),
            )
        )
        order_offset = 1

    for i, match in enumerate(matches):
        # The first chapter absorbs all pre-heading text from unit 0.
        if i == 0 and order_offset == 0:
            start_unit, start_offset = 0, 0
        else:
            start_unit, start_offset = match.unit_index, match.line_start

        if i + 1 < len(matches):
            next_match = matches[i + 1]
            end_unit, end_offset = next_match.unit_index, next_match.line_start
        else:
            end_unit, end_offset = last_unit_index, eof_offset

        chapter_order = i + order_offset
        chapter_id = chapter_ids[i]
        display_name = _derive_display_name(text_units, match, patterns)
        slices = _collect_slices(text_units, start_unit, start_offset, end_unit, end_offset)

        splits.append(
            ChapterSplit(
                index_entry=ChapterIndexEntry(
                    chapter_id=chapter_id,
                    order=chapter_order,
                    segments_file=f"segments/{chapter_id}.json",
                    display_name=display_name,
                ),
                slices=slices,
            )
        )

    return tuple(splits)


def _derive_display_name(
    text_units: tuple[PreparedTextUnit, ...],
    match: _HeadingMatch,
    patterns: list[re.Pattern[str]],
) -> str:
    display_name = unicodedata.normalize("NFC", match.line_text).strip()
    if not display_name.endswith(":"):
        return display_name

    unit_text = text_units[match.unit_index].text
    for line_start, line_text in _iter_lines(unit_text):
        if line_start <= match.line_start:
            continue
        candidate = unicodedata.normalize("NFC", line_text).strip()
        if not candidate:
            continue
        if _try_match(patterns, candidate).matched:
            return display_name
        return f"{display_name} {candidate}"

    return display_name


def _should_synthesize_front_matter(
    text_units: tuple[PreparedTextUnit, ...],
    first_match: _HeadingMatch,
) -> bool:
    if first_match.num is None:
        return False

    pre_heading_text_parts = [unit.text for unit in text_units[: first_match.unit_index]]
    pre_heading_text_parts.append(
        text_units[first_match.unit_index].text[: first_match.line_start]
    )
    return bool("".join(pre_heading_text_parts).strip())


def _collect_front_matter_slices(
    text_units: tuple[PreparedTextUnit, ...],
    first_match: _HeadingMatch,
) -> tuple[UnitSlice, ...]:
    if first_match.unit_index == 0:
        return _collect_slices(text_units, 0, 0, 0, first_match.line_start)

    slices = list(
        _collect_slices(
            text_units,
            0,
            0,
            first_match.unit_index - 1,
            len(text_units[first_match.unit_index - 1].text),
        )
    )
    if first_match.line_start > 0:
        slices.extend(
            _collect_slices(
                text_units,
                first_match.unit_index,
                0,
                first_match.unit_index,
                first_match.line_start,
            )
        )
    return tuple(slices)


def _derive_chapter_ids(
    matches: list[_HeadingMatch],
    subchapters_enabled: bool,
) -> tuple[str, ...]:
    numbered_anchors = [
        _NumberedAnchor(match_index=i, base=_num_base_int(match.num))
        for i, match in enumerate(matches)
        if match.num is not None
    ]
    seen_bases: dict[str, int] = {}
    front_matter_count = 0
    back_matter_count = 0
    between_matter_counts: dict[int, int] = {}
    chapter_ids: list[str] = []

    for i, match in enumerate(matches):
        if match.num is not None:
            chapter_ids.append(
                _derive_numbered_chapter_id(match.num, seen_bases, subchapters_enabled)
            )
            continue

        ordinal_1_indexed = i + 1
        chapter_ids.append(
            _derive_non_numbered_chapter_id(
                ordinal_1_indexed=ordinal_1_indexed,
                numbered_anchors=numbered_anchors,
                match_index=i,
                front_matter_count=front_matter_count,
                back_matter_count=back_matter_count,
                between_matter_counts=between_matter_counts,
            )
        )

        if not numbered_anchors:
            continue
        previous_anchor = _previous_numbered_anchor(numbered_anchors, i)
        next_anchor = _next_numbered_anchor(numbered_anchors, i)
        if previous_anchor is None:
            front_matter_count += 1
        elif next_anchor is None:
            back_matter_count += 1
        else:
            between_matter_counts[previous_anchor.match_index] = (
                between_matter_counts.get(previous_anchor.match_index, 0) + 1
            )

    return tuple(chapter_ids)


def _derive_non_numbered_chapter_id(
    *,
    ordinal_1_indexed: int,
    numbered_anchors: list[_NumberedAnchor],
    match_index: int,
    front_matter_count: int,
    back_matter_count: int,
    between_matter_counts: dict[int, int],
) -> str:
    if not numbered_anchors:
        return f"chapter_{ordinal_1_indexed:02d}"

    previous_anchor = _previous_numbered_anchor(numbered_anchors, match_index)
    next_anchor = _next_numbered_anchor(numbered_anchors, match_index)

    if previous_anchor is None:
        if front_matter_count == 0:
            return "chapter_00"
        return f"chapter_00_{front_matter_count + 1}"
    if next_anchor is None:
        chapter_num = max(anchor.base for anchor in numbered_anchors) + back_matter_count + 1
        return f"chapter_{_two_digit_chapter_num(chapter_num)}"

    suffix = between_matter_counts.get(previous_anchor.match_index, 0) + 1
    # Recurrent numbered subchapter suffixes also use `_N` when subchapters
    # are enabled. If a recurrent `Chapter N` and an interlude both occupy the
    # same gap, their ids can theoretically collide; the stage-local validator
    # surfaces that rare duplicate instead of silently renumbering.
    return f"chapter_{_two_digit_chapter_num(previous_anchor.base)}_{suffix}"


def _previous_numbered_anchor(
    numbered_anchors: list[_NumberedAnchor],
    match_index: int,
) -> _NumberedAnchor | None:
    previous = [anchor for anchor in numbered_anchors if anchor.match_index < match_index]
    if not previous:
        return None
    return previous[-1]


def _next_numbered_anchor(
    numbered_anchors: list[_NumberedAnchor],
    match_index: int,
) -> _NumberedAnchor | None:
    for anchor in numbered_anchors:
        if anchor.match_index > match_index:
            return anchor
    return None


def _collect_slices(
    text_units: tuple[PreparedTextUnit, ...],
    start_unit: int,
    start_offset: int,
    end_unit: int,
    end_offset: int,
) -> tuple[UnitSlice, ...]:
    slices: list[UnitSlice] = []
    for u_idx in range(start_unit, end_unit + 1):
        unit = text_units[u_idx]
        s = start_offset if u_idx == start_unit else 0
        e = end_offset if u_idx == end_unit else len(unit.text)
        slices.append(
            UnitSlice(
                text_unit_id=unit.text_unit_id,
                text=unit.text[s:e],
                needs_review=unit.needs_review,
            )
        )
    return tuple(slices)


def _derive_numbered_chapter_id(
    num: str | None,
    seen_bases: dict[str, int],
    subchapters_enabled: bool,
) -> str:
    if num is None:
        raise ValueError("numbered chapter id derivation requires a captured num")
    if "." in num:
        base_int, sub_int = num.split(".", 1)
        return f"chapter_{_two_digit_chapter_num(int(base_int))}_{int(sub_int)}"
    base = _two_digit_chapter_num(int(num))
    seen_bases[base] = seen_bases.get(base, 0) + 1
    if subchapters_enabled and seen_bases[base] > 1:
        return f"chapter_{base}_{seen_bases[base]}"
    return f"chapter_{base}"


def _num_base_int(num: str | None) -> int:
    if num is None:
        raise ValueError("chapter num is required")
    return int(num.split(".", 1)[0])


def _two_digit_chapter_num(num: int) -> str:
    if num > 99:
        raise ValueError(f"chapter number {num} exceeds chapter_id two-digit range")
    return f"{num:02d}"
