"""Stage 4: ATTRIBUTE — Assign speakers to dialogue segments via LLM.

Takes parsed chapters and uses an LLM to determine who speaks each
dialogue and inner thought segment. Narration segments are automatically
attributed to the POV character (or NARRATOR if no POV is set).

The key algorithm is scene-aware windowing: segments are grouped by scene
(split at SCENE_BREAK), then processed in overlapping windows so the LLM
has enough context for accurate attribution.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .models import Chapter, CharacterRegistry, Segment, SegmentType


def group_by_scene(segments: tuple[Segment, ...]) -> list[list[Segment]]:
    """Split a chapter's segments into scenes at SCENE_BREAK boundaries.

    Each scene is a list of consecutive segments between scene breaks.
    The scene break segments themselves are not included in any scene
    (they don't need attribution).

    Args:
        segments: All segments from a chapter.

    Returns:
        List of scenes, where each scene is a list of Segments.
    """
    ...


def create_windows(
    scene: list[Segment], window_size: int = 40, overlap: int = 8
) -> list[list[Segment]]:
    """Split a scene into overlapping windows for LLM processing.

    If a scene has fewer segments than window_size, it becomes a single
    window. Otherwise, windows advance by (window_size - overlap) segments.

    Args:
        scene: Segments within a single scene.
        window_size: Maximum segments per window.
        overlap: Number of segments shared between consecutive windows.

    Returns:
        List of windows, each a list of Segments.
    """
    ...


def attribute_narration(
    chapter: Chapter, narrator_name: str = "Narrator"
) -> Chapter:
    """Set speaker for all narration and header segments.

    Narration gets pov_character if set, else narrator_name.
    Chapter headers always get narrator_name.
    Scene breaks get no speaker (left as None).
    Dialogue and inner_thought are left unchanged (for LLM attribution).

    Args:
        chapter: Chapter with unattributed segments.
        narrator_name: Name to use for the narrator voice.

    Returns:
        New Chapter with narration segments attributed.
    """
    ...


def attribute_chapter(
    chapter: Chapter,
    registry: CharacterRegistry,
    llm_provider: str = "openrouter",
    llm_model: str | None = None,
) -> Chapter:
    """Run full attribution on a chapter: narration + LLM dialogue attribution.

    Orchestrates the full attribution pipeline:
    1. Attribute narration/headers automatically
    2. Group remaining dialogue/thought segments by scene
    3. Window each scene and send to LLM
    4. Merge LLM attributions back into the chapter

    Args:
        chapter: Parsed chapter with unattributed segments.
        registry: Character registry for the book.
        llm_provider: LLM provider to use (default: openrouter).
        llm_model: Specific model to use, or None for config default.

    Returns:
        New Chapter with all segments attributed (speaker + confidence).
    """
    ...
