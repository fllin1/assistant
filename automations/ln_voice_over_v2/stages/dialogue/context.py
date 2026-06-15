"""Pure context payload construction for dialogue attribution."""

from __future__ import annotations

from typing import Literal

from ...common.artifacts import ContractModel
from ...common.ids import ChapterId, SegmentId, SeriesId, VolumeId
from ...series.contracts import StoryProfile
from ..transform.contracts import Segment, SegmentFile


class PayloadSegment(ContractModel):
    """One segment included in a chapter-level dialogue attribution payload."""

    segment_id: SegmentId
    text: str
    role: Literal["candidate", "narration", "context"]


class ChapterPayload(ContractModel):
    """Whole-chapter payload sent to the dialogue attribution boundary."""

    series: SeriesId
    volume: VolumeId
    chapter_id: ChapterId
    narrator_hint: str | None
    segments: tuple[PayloadSegment, ...]
    candidate_ids: tuple[SegmentId, ...]


def select_candidates(segment_file: SegmentFile) -> tuple[Segment, ...]:
    """Return quote-candidate segments in their existing chapter order.

    Args:
        segment_file: Chapter segment artifact to scan.

    Returns:
        Segments whose parser hints explicitly mark them as quote candidates.
    """
    return tuple(
        segment
        for segment in segment_file.segments
        if segment.parser_hints.get("quote_candidate") is True
    )


def build_chapter_payload(
    segment_file: SegmentFile, story_profile: StoryProfile | None = None
) -> ChapterPayload:
    """Build a whole-chapter dialogue payload without rewriting segment text.

    Args:
        segment_file: Chapter segment artifact to serialize.
        story_profile: Optional story profile supplying a default narrator hint.

    Returns:
        Whole-chapter dialogue attribution payload.
    """
    candidate_ids = tuple(segment.segment_id for segment in select_candidates(segment_file))
    candidate_id_set = set(candidate_ids)
    narrator_hint = (
        story_profile.rules.get("default_narrator") if story_profile is not None else None
    )

    return ChapterPayload(
        series=segment_file.series,
        volume=segment_file.volume,
        chapter_id=segment_file.chapter_id,
        narrator_hint=narrator_hint,
        segments=tuple(
            PayloadSegment(
                segment_id=segment.segment_id,
                text=segment.text,
                role="candidate" if segment.segment_id in candidate_id_set else "narration",
            )
            for segment in segment_file.segments
        ),
        candidate_ids=candidate_ids,
    )
