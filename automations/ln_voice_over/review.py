"""REVIEW-stage construction and validation for canonical Chapter artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import Chapter, CharacterRegistry, Segment, SegmentType

RESERVED_SPEAKERS = {"Narrator", "Unknown"}


class ReviewValidationError(ValueError):
    """Raised when a reviewed Chapter would violate the canonical contract."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        message = "REVIEW validation failed:\n" + "\n".join(f"- {p}" for p in self.problems)
        super().__init__(message)


def build_reviewed_chapter(
    parsed_chapter: Chapter,
    original_attributions: Mapping[str, str],
    corrections: Iterable[Mapping[str, object]],
    registry: CharacterRegistry,
) -> tuple[Chapter, list[dict]]:
    """Build a reviewed Chapter and audit changes from judge corrections.

    REVIEW is the first hard-validation boundary. Intermediate attribution maps
    may contain aliases or raw LLM names; this module canonicalises what it can
    and refuses to produce reviewed output while any Registry gap remains.
    """
    overrides = _canonical_overrides(corrections, parsed_chapter, registry)
    changes: list[dict] = []
    reviewed_segments: list[Segment] = []

    for segment in parsed_chapter.segments:
        if segment.segment_type in (SegmentType.CHAPTER_HEADER, SegmentType.NARRATION):
            reviewed_segments.append(segment.model_copy(update={"speaker": "Narrator"}))
            continue

        if segment.segment_type == SegmentType.SCENE_BREAK:
            reviewed_segments.append(segment.model_copy(update={"speaker": None}))
            continue

        original_speaker = _canonicalise_attribution(
            original_attributions.get(str(segment.index)),
            parsed_chapter,
            registry,
        )
        speaker = overrides.get(segment.index, original_speaker)
        if segment.index in overrides and speaker != original_speaker:
            changes.append({"index": segment.index, "old": original_speaker, "new": speaker})

        reviewed_segments.append(segment.model_copy(update={"speaker": speaker}))

    reviewed = parsed_chapter.model_copy(
        update={"segments": tuple(reviewed_segments), "reviewed": True}
    )
    validate_reviewed_chapter(reviewed, registry)
    return reviewed, changes


def validate_reviewed_chapter(chapter: Chapter, registry: CharacterRegistry) -> None:
    """Validate the canonical Speaker grammar for reviewed Chapter data."""
    problems: list[str] = []

    for segment in chapter.segments:
        prefix = f"segment {segment.index} ({segment.segment_type.value})"

        if segment.segment_type in (SegmentType.CHAPTER_HEADER, SegmentType.NARRATION):
            if segment.speaker != "Narrator":
                problems.append(f'{prefix} must use speaker "Narrator"')
            continue

        if segment.segment_type == SegmentType.SCENE_BREAK:
            if segment.speaker is not None:
                problems.append(f"{prefix} must use speaker null")
            continue

        if segment.segment_type == SegmentType.DIALOGUE:
            if segment.speaker is None:
                problems.append(f"{prefix} is missing a speaker")
                continue
            if segment.speaker == "I":
                problems.append(f'{prefix} cannot use unresolved speaker "I"')
                continue
            if segment.speaker in RESERVED_SPEAKERS:
                continue
            character = registry.find(segment.speaker)
            if character is None:
                problems.append(f"{prefix} has unresolved Registry gap: {segment.speaker!r}")
            elif character.name != segment.speaker:
                problems.append(
                    f"{prefix} must use canonical speaker {character.name!r}, "
                    f"not {segment.speaker!r}"
                )

    if problems:
        raise ReviewValidationError(problems)


def _canonical_overrides(
    corrections: Iterable[Mapping[str, object]],
    chapter: Chapter,
    registry: CharacterRegistry,
) -> dict[int, str | None]:
    overrides: dict[int, str | None] = {}
    for correction in corrections:
        index = int(correction["index"])
        raw_speaker = correction.get("speaker")
        speaker = raw_speaker if isinstance(raw_speaker, str) else None
        overrides[index] = _canonicalise_attribution(speaker, chapter, registry)
    return overrides


def _canonicalise_attribution(
    raw: str | None,
    chapter: Chapter,
    registry: CharacterRegistry,
) -> str | None:
    if raw is None:
        return None

    speaker = raw.strip()
    if not speaker:
        return None
    if speaker in RESERVED_SPEAKERS:
        return speaker
    if speaker == "I" and chapter.narrator:
        return _canonicalise_character(chapter.narrator, registry)

    return _canonicalise_character(speaker, registry)


def _canonicalise_character(raw: str, registry: CharacterRegistry) -> str:
    character = registry.find(raw) or registry.fuzzy_find(raw)
    return character.name if character else raw
