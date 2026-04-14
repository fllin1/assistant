"""Stage 4: ATTRIBUTE — Assign speakers to dialogue segments via LLM.

Takes parsed chapters and uses an LLM to determine who speaks each
dialogue segment. Narration segments are automatically attributed to
the POV character (or "Narrator" if no POV is set).

Segments are processed in overlapping windows so the LLM has enough
context for accurate attribution without exceeding context limits.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from ollama import chat

from .config import (
    ATTRIBUTION_WINDOW_OVERLAP,
    ATTRIBUTION_WINDOW_SIZE,
    DEFAULT_LLM_MODEL,
    PREVIOUS_ATTRIBUTIONS_SIZE,
)
from .models import Chapter, CharacterRegistry, Segment, SegmentType
from .prompts import (
    build_attribution_prompt,
    build_single_attribution_prompt,
    build_system_prompt,
    parse_attribution_response,
)

logger = logging.getLogger(__name__)


def _call_llm(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
    resolved_model = model or DEFAULT_LLM_MODEL
    response = chat(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response["message"]["content"]


def create_windows(
    segments: tuple[Segment, ...] | list[Segment],
    window_size: int = ATTRIBUTION_WINDOW_SIZE,
    overlap: int = ATTRIBUTION_WINDOW_OVERLAP,
) -> list[list[Segment]]:
    """Split segments into overlapping windows for LLM processing.

    If there are fewer segments than window_size, returns a single window.
    Otherwise, windows advance by (window_size - overlap) segments.

    Args:
        segments: Segments to window.
        window_size: Maximum segments per window.
        overlap: Number of segments shared between consecutive windows.

    Returns:
        List of windows, each a list of Segments.
    """
    seg_list = list(segments)
    if len(seg_list) <= window_size:
        return [seg_list]

    stride = window_size - overlap
    windows = []
    for start in range(0, len(seg_list), stride):
        window = seg_list[start : start + window_size]
        windows.append(window)
        # Stop if this window reaches the end
        if start + window_size >= len(seg_list):
            break
    return windows


def attribute_narration(chapter: Chapter, narrator_name: str = "Narrator") -> Chapter:
    """Set speaker for all narration and header segments.

    Narration gets pov_character if set, else narrator_name.
    Chapter headers always get narrator_name.
    Dialogue is left unchanged (for LLM attribution).

    Args:
        chapter: Chapter with unattributed segments.
        narrator_name: Name to use for the narrator voice.

    Returns:
        New Chapter with narration segments attributed.
    """
    narration_speaker = chapter.pov_character or narrator_name
    new_segments = []

    for seg in chapter.segments:
        if seg.segment_type == SegmentType.CHAPTER_HEADER:
            new_segments.append(
                replace(
                    seg,
                    speaker=narrator_name,
                    confidence=1.0,
                    attribution_method="narration_auto",
                )
            )
        elif seg.segment_type == SegmentType.NARRATION:
            new_segments.append(
                replace(
                    seg,
                    speaker=narration_speaker,
                    confidence=1.0,
                    attribution_method="narration_auto",
                )
            )
        else:
            new_segments.append(seg)

    return replace(chapter, segments=tuple(new_segments))


def attribute_chapter(
    chapter: Chapter,
    registry: CharacterRegistry,
    llm_model: str | None = None,
) -> Chapter:
    """Run full attribution on a chapter: narration + LLM dialogue attribution.

    Orchestrates the full attribution pipeline:
    1. Attribute narration/headers automatically
    2. Window the chapter segments
    3. For each window, call the LLM (Ollama) and merge attributions
    4. Fall back to "Unknown" for any unattributed dialogue

    Args:
        chapter: Parsed chapter with unattributed segments.
        registry: Character registry for the book.
        llm_model: Specific model to use, or None for config default.

    Returns:
        New Chapter with all segments attributed (speaker + confidence).
    """
    # Step 1: auto-attribute narration
    chapter = attribute_narration(chapter, registry.narrator_name)

    # Build index → segment mapping for merging
    seg_by_index: dict[int, Segment] = {s.index: s for s in chapter.segments}

    # Step 2: window and attribute dialogue via LLM
    system_prompt = build_system_prompt()
    windows = create_windows(chapter.segments)
    previous_attributions: list[dict] | None = None

    for i, window in enumerate(windows):
        # Only call LLM if window has unattributed dialogue
        has_dialogue = any(
            s.segment_type == SegmentType.DIALOGUE and s.speaker is None for s in window
        )
        if not has_dialogue:
            continue

        user_prompt = build_attribution_prompt(window, registry, previous_attributions)

        logger.info(
            "Window %d/%d (%d segments, %d dialogue)",
            i + 1,
            len(windows),
            len(window),
            sum(1 for s in window if s.segment_type == SegmentType.DIALOGUE),
        )

        raw_response = _call_llm(system_prompt, user_prompt, llm_model)
        attributions = parse_attribution_response(raw_response)

        # Merge attributions into segments with registry validation
        for attr in attributions:
            idx = attr["index"]
            if idx in seg_by_index and seg_by_index[idx].speaker is None:
                speaker, confidence = registry.validate_speaker(
                    attr["speaker"], attr["confidence"]
                )
                seg_by_index[idx] = replace(
                    seg_by_index[idx],
                    speaker=speaker,
                    confidence=confidence,
                    attribution_method="windowed_llm",
                )

        # Build context for next window from this window's attributions
        previous_attributions = [
            {
                "index": s.index,
                "segment_type": s.segment_type.value,
                "text": s.text[:80],
                "speaker": seg_by_index[s.index].speaker or "Unknown",
            }
            for s in window[-5:]
            if s.segment_type == SegmentType.DIALOGUE
        ]

    # Step 3: fallback for any remaining unattributed dialogue
    for idx, seg in seg_by_index.items():
        if seg.segment_type == SegmentType.DIALOGUE and seg.speaker is None:
            seg_by_index[idx] = replace(
                seg, speaker="Unknown", confidence=0.0, attribution_method="fallback"
            )

    # Rebuild chapter with attributed segments in original order
    final_segments = tuple(seg_by_index[s.index] for s in chapter.segments)
    return replace(chapter, segments=final_segments)


def attribute_chapter_per_dialogue(
    chapter: Chapter,
    registry: CharacterRegistry,
    llm_model: str | None = None,
    context_size: int = 2,
) -> Chapter:
    """Attribute each dialogue segment individually with surrounding context.

    Makes one LLM call per dialogue segment, passing context_size segments
    before and after as context. Slower but more accurate than windowed.

    Args:
        chapter: Parsed chapter with unattributed segments.
        registry: Character registry for the book.
        llm_model: Specific model to use, or None for config default.
        context_size: Number of segments before/after for context.

    Returns:
        New Chapter with all segments attributed.
    """
    chapter = attribute_narration(chapter, registry.narrator_name)
    segments = list(chapter.segments)

    system_prompt = build_system_prompt()
    dialogue_indices = [
        i for i, s in enumerate(segments) if s.segment_type == SegmentType.DIALOGUE
    ]

    logger.info("%d dialogue segments to attribute", len(dialogue_indices))

    previous_attributions: list[dict] = []

    for count, seg_i in enumerate(dialogue_indices):
        seg = segments[seg_i]

        # Gather context window and call LLM
        start = max(0, seg_i - context_size)
        end = min(len(segments), seg_i + context_size + 1)
        context = segments[start:end]

        user_prompt = build_single_attribution_prompt(
            context,
            seg.index,
            registry,
            previous_attributions=previous_attributions or None,
        )
        raw_response = _call_llm(system_prompt, user_prompt, llm_model)
        attributions = parse_attribution_response(raw_response)

        if attributions:
            attr = attributions[0]
            speaker, confidence = registry.validate_speaker(attr["speaker"], attr["confidence"])
            if speaker != "Unknown":
                segments[seg_i] = replace(
                    seg,
                    speaker=speaker,
                    confidence=confidence,
                    attribution_method="per_dialogue_llm",
                )
            else:
                segments[seg_i] = replace(
                    seg,
                    speaker="Unknown",
                    confidence=0.0,
                    attribution_method="fallback",
                )
        else:
            segments[seg_i] = replace(
                seg,
                speaker="Unknown",
                confidence=0.0,
                attribution_method="fallback",
            )

        # Update rolling context for next LLM call
        previous_attributions.append(
            {
                "index": seg.index,
                "text": seg.text[:80],
                "speaker": segments[seg_i].speaker,
            }
        )
        previous_attributions = previous_attributions[-PREVIOUS_ATTRIBUTIONS_SIZE:]

        if (count + 1) % 50 == 0:
            logger.info("Progress: %d/%d", count + 1, len(dialogue_indices))

    return replace(chapter, segments=tuple(segments))
