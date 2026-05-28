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

    return _build_chapter_splits(text_units, matches, subchapters_enabled)


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
    subchapters_enabled: bool,
) -> tuple[ChapterSplit, ...]:
    seen_bases: dict[str, int] = {}
    splits: list[ChapterSplit] = []
    last_unit_index = len(text_units) - 1
    eof_offset = len(text_units[last_unit_index].text)

    for i, match in enumerate(matches):
        # The first chapter absorbs all pre-heading text from unit 0.
        if i == 0:
            start_unit, start_offset = 0, 0
        else:
            start_unit, start_offset = match.unit_index, match.line_start

        if i + 1 < len(matches):
            next_match = matches[i + 1]
            end_unit, end_offset = next_match.unit_index, next_match.line_start
        else:
            end_unit, end_offset = last_unit_index, eof_offset

        chapter_order = i
        ordinal_1_indexed = chapter_order + 1
        chapter_id = _derive_chapter_id(
            match.num, ordinal_1_indexed, seen_bases, subchapters_enabled
        )
        display_name = unicodedata.normalize("NFC", match.line_text).strip()
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


def _derive_chapter_id(
    num: str | None,
    ordinal_1_indexed: int,
    seen_bases: dict[str, int],
    subchapters_enabled: bool,
) -> str:
    if num is None:
        return f"chapter_{ordinal_1_indexed:02d}"
    if "." in num:
        base_int, sub_int = num.split(".", 1)
        return f"chapter_{int(base_int):02d}_{int(sub_int)}"
    base = f"{int(num):02d}"
    seen_bases[base] = seen_bases.get(base, 0) + 1
    if subchapters_enabled and seen_bases[base] > 1:
        return f"chapter_{base}_{seen_bases[base]}"
    return f"chapter_{base}"
