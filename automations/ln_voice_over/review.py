"""Stage 5: REVIEW — Correction of speaker attributions.

Provides tools for inspecting LLM-attributed segments and fixing
mistakes before TTS synthesis. The primary interface is the
/review-chapter Claude skill, which reads context and resolves
divergences. This module supports the CLI path and programmatic use.

This stage is deliberately separate from attribution so corrections
persist independently of re-runs.
"""

from __future__ import annotations

from .models import Chapter


def apply_correction(chapter: Chapter, segment_index: int, new_speaker: str) -> Chapter:
    """Create a new Chapter with one segment's speaker corrected."""
    new_segments = []
    for seg in chapter.segments:
        if seg.index == segment_index:
            new_segments.append(seg.model_copy(update={"speaker": new_speaker}))
        else:
            new_segments.append(seg)
    return chapter.model_copy(update={"segments": tuple(new_segments)})


def approve_chapter(chapter: Chapter) -> Chapter:
    """Mark a chapter as reviewed without changes."""
    return chapter.model_copy(update={"reviewed": True})
