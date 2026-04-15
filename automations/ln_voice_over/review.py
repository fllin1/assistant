"""Stage 5: REVIEW — Correction of speaker attributions.

Provides tools for inspecting LLM-attributed segments and fixing
mistakes before TTS synthesis. The primary interface is the
/review-chapter Claude skill, which reads context and resolves
divergences. This module supports the CLI path and programmatic use.

This stage is deliberately separate from attribution so corrections
persist independently of re-runs.
"""

from __future__ import annotations

from dataclasses import replace

from .models import Chapter, Segment, SegmentType


def get_low_confidence_segments(chapter: Chapter, threshold: float = 0.7) -> list[Segment]:
    """Return dialogue segments with confidence below the threshold.

    Args:
        chapter: Attributed chapter.
        threshold: Confidence cutoff (0.0-1.0).

    Returns:
        List of Segments needing review, sorted by index.
    """
    return sorted(
        [
            s
            for s in chapter.segments
            if s.segment_type == SegmentType.DIALOGUE
            and s.confidence is not None
            and s.confidence < threshold
        ],
        key=lambda s: s.index,
    )


def apply_correction(chapter: Chapter, segment_index: int, new_speaker: str) -> Chapter:
    """Create a new Chapter with one segment's speaker corrected.

    Sets the corrected segment's confidence to 1.0 (human-verified).
    """
    new_segments = []
    for seg in chapter.segments:
        if seg.index == segment_index:
            new_segments.append(
                replace(seg, speaker=new_speaker, confidence=1.0, attribution_method="reviewed")
            )
        else:
            new_segments.append(seg)
    return replace(chapter, segments=tuple(new_segments))


def approve_chapter(chapter: Chapter) -> Chapter:
    """Mark a chapter as reviewed without changes."""
    return replace(chapter, reviewed=True)
