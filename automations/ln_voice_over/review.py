"""Stage 5: REVIEW — Manual correction of speaker attributions.

Provides tools for the user to inspect LLM-attributed segments and fix
mistakes before TTS synthesis. Two modes:

1. CLI interactive: prints segments with color-coded attributions,
   highlights low-confidence items, prompts for corrections.
2. Direct file editing: attributed JSON is human-readable and can be
   edited in any text editor, then copied to reviewed/.

This stage is deliberately separate from attribution so corrections
persist independently of re-runs.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .models import Chapter, Segment


def get_low_confidence_segments(
    chapter: Chapter, threshold: float = 0.7
) -> list[Segment]:
    """Return segments with confidence below the threshold.

    Args:
        chapter: Attributed chapter.
        threshold: Confidence cutoff (0.0-1.0).

    Returns:
        List of Segments needing review, sorted by index.
    """
    ...


def apply_correction(
    chapter: Chapter, segment_index: int, new_speaker: str
) -> Chapter:
    """Create a new Chapter with one segment's speaker corrected.

    Sets the corrected segment's confidence to 1.0 (human-verified).

    Args:
        chapter: The chapter to correct.
        segment_index: Index of the segment to fix.
        new_speaker: Corrected speaker name.

    Returns:
        New Chapter with the correction applied.
    """
    ...


def approve_chapter(chapter: Chapter) -> Chapter:
    """Mark a chapter as reviewed without changes.

    Sets reviewed=True on the chapter.

    Args:
        chapter: Attributed chapter to approve.

    Returns:
        New Chapter with reviewed=True.
    """
    ...


def display_segments_for_review(
    chapter: Chapter,
    only_low_confidence: bool = False,
    threshold: float = 0.7,
) -> None:
    """Print chapter segments with color-coded attributions.

    Uses rich for colored output:
    - Narration in dim/gray
    - Dialogue in white with speaker name colored
    - Low-confidence segments highlighted in yellow
    - Scene breaks as horizontal rules

    Args:
        chapter: Chapter to display.
        only_low_confidence: If True, show only flagged segments.
        threshold: Confidence threshold for highlighting.
    """
    ...
