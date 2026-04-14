"""Step 1: Speaker mention extraction from narration context.

Extracts WHO is speaking each dialogue segment by analyzing surrounding
narration for speech tags, pronouns, and conversational flow. Does NOT
resolve mentions to canonical registry names — that's Step 2.

Each dialogue gets an LLM call with ±context_size surrounding segments.
The LLM returns the raw mention (name/pronoun/null), its best guess at
the character, the narration source, and brief reasoning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ollama import chat

from .models import Chapter, Segment, SegmentType

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Pronouns for mention_type classification
_PRONOUNS = {"he", "she", "they", "her", "him", "his"}
_FIRST_PERSON = {"i", "me", "my"}


def load_prompt_template(version: str) -> str:
    """Load a versioned prompt template from the prompts/ directory."""
    path = PROMPTS_DIR / f"extraction_{version}.txt"
    return path.read_text(encoding="utf-8")


def classify_mention_type(raw_mention: str | None) -> str:
    """Derive mention_type from raw_mention text."""
    if raw_mention is None:
        return "none"
    lower = raw_mention.lower().strip()
    if lower in _FIRST_PERSON:
        return "first_person"
    if lower in _PRONOUNS:
        return "pronoun"
    return "name"


def _call_llm(system_prompt: str, user_prompt: str, model: str) -> str:
    response = chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response["message"]["content"]


def _build_user_prompt(
    target_index: int,
    segments: list[Segment],
    context_before: int,
    context_after: int,
    pov_character: str | None,
    previous_attributions: list[dict] | None = None,
) -> str:
    """Build the user prompt with context segments around the target dialogue."""
    # Find position of target in the segment list
    pos = next(i for i, s in enumerate(segments) if s.index == target_index)

    start = max(0, pos - context_before)
    end = min(len(segments), pos + context_after + 1)
    context = segments[start:end]

    lines = []
    if pov_character:
        lines.append(f"Narrator: {pov_character}")
    lines.append("")

    if previous_attributions:
        lines.append("# Recent attributions")
        lines.append("")
        for attr in previous_attributions:
            text_preview = attr.get("text", "")[:60]
            lines.append(f'- [idx {attr["index"]}] "{text_preview}..." → {attr["speaker"]}')
        lines.append("")

    lines.append("# Context")
    lines.append("")

    for seg in context:
        seg_type = seg.segment_type.value
        marker = " <<<< WHO SPEAKS THIS?" if seg.index == target_index else ""
        lines.append(f"[{seg_type}] [idx {seg.index}] {seg.text[:500]}{marker}")

    lines.append("")
    lines.append(f"Who is speaking the dialogue at index {target_index}?")

    return "\n".join(lines)


def parse_extraction_response(response: str) -> dict | None:
    """Parse the LLM's extraction response into a structured dict.

    Returns dict with keys: raw_mention, resolved_mention,
    mention_source_index, mention_type, reasoning. Returns None on failure.
    """
    text = response.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try to extract JSON from the response
    # Sometimes models wrap JSON in extra text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        logger.warning("No JSON object found in response: %s", text[:200])
        return None

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("Failed to parse extraction response: %s", text[:200])
        return None

    return {
        "raw_mention": data.get("raw_mention"),
        "resolved_mention": data.get("resolved_mention"),
        "mention_source_index": data.get("mention_source_index"),
        "mention_type": data.get("mention_type", "none"),
        "reasoning": data.get("reasoning", ""),
    }


def _validate_source_index(result: dict, segments: list[Segment]) -> dict:
    """Verify that mention_source_index actually contains raw_mention."""
    source_idx = result.get("mention_source_index")
    raw = result.get("raw_mention")
    if source_idx is None or raw is None:
        return result

    # Find the source segment
    source_seg = next((s for s in segments if s.index == source_idx), None)
    if source_seg is None:
        result["_source_valid"] = False
        return result

    if raw.lower() in source_seg.text.lower():
        result["_source_valid"] = True
    else:
        result["_source_valid"] = False
        logger.debug(
            "Source index %d does not contain '%s': %s",
            source_idx,
            raw,
            source_seg.text[:80],
        )

    return result


def extract_mention(
    dialogue_index: int,
    segments: list[Segment],
    context_before: int = 5,
    context_after: int = 5,
    pov_character: str | None = None,
    model: str = "gemma4:26b",
    prompt_version: str = "v1",
    previous_attributions: list[dict] | None = None,
) -> dict:
    """Extract speaker mention for a single dialogue segment.

    Args:
        dialogue_index: The segment index of the target dialogue.
        segments: All segments in the chapter.
        context_before: Number of segments before the dialogue for context.
        context_after: Number of segments after the dialogue for context.
        pov_character: Name of the first-person narrator for this segment.
        model: Ollama model tag.
        prompt_version: Prompt template version (e.g. "v1").
        previous_attributions: Recent attributions for conversational context.
            Each dict has keys: index, text, speaker.

    Returns:
        Dict with keys: index, raw_mention, resolved_mention,
        mention_source_index, mention_position, mention_type,
        reasoning, model, _source_valid.
    """
    system_prompt = load_prompt_template(prompt_version).format(
        pov_character=pov_character or "unknown narrator"
    )
    user_prompt = _build_user_prompt(
        dialogue_index,
        segments,
        context_before,
        context_after,
        pov_character,
        previous_attributions,
    )

    raw_response = _call_llm(system_prompt, user_prompt, model)
    parsed = parse_extraction_response(raw_response)

    if parsed is None:
        parsed = {
            "raw_mention": None,
            "resolved_mention": None,
            "mention_source_index": None,
            "mention_type": "none",
            "reasoning": "Failed to parse LLM response",
        }

    # Override mention_type with our deterministic classification
    parsed["mention_type"] = classify_mention_type(parsed.get("raw_mention"))

    # Derive mention_position from indices
    source_idx = parsed.get("mention_source_index")
    if source_idx is not None:
        parsed["mention_position"] = "before" if source_idx < dialogue_index else "after"
    else:
        parsed["mention_position"] = None

    # Add metadata
    parsed["index"] = dialogue_index
    parsed["model"] = model

    # Validate source index
    parsed = _validate_source_index(parsed, segments)

    return parsed


def extract_chapter_mentions(
    chapter: Chapter,
    model: str = "gemma4:26b",
    context_before: int = 5,
    context_after: int = 5,
    prompt_version: str = "v1",
    pov_character: str | None = None,
    batch_range: tuple[int, int] | None = None,
    use_rolling_context: bool = False,
    rolling_context_size: int = 5,
) -> list[dict]:
    """Run mention extraction on all (or a batch of) dialogues in a chapter.

    Args:
        chapter: Parsed chapter with segments.
        model: Ollama model tag.
        context_before: Segments before the dialogue for context.
        context_after: Segments after the dialogue for context.
        prompt_version: Prompt template version.
        pov_character: Override POV character (uses chapter.pov_character if None).
        batch_range: Optional (start, end) slice into dialogue indices.
        use_rolling_context: Pass recent attributions to each LLM call.
        rolling_context_size: Number of recent attributions to include.

    Returns:
        List of extraction dicts, one per dialogue segment.
    """
    segments = list(chapter.segments)
    dialogue_positions = [
        i for i, s in enumerate(segments) if s.segment_type == SegmentType.DIALOGUE
    ]

    if batch_range:
        start, end = batch_range
        dialogue_positions = dialogue_positions[start:end]

    resolved_pov = pov_character or chapter.pov_character

    logger.info(
        "Extracting mentions: %d dialogues, model=%s, prompt=%s, context=-%d/+%d, rolling=%s",
        len(dialogue_positions),
        model,
        prompt_version,
        context_before,
        context_after,
        use_rolling_context,
    )

    results = []
    previous_attributions: list[dict] = []

    for count, pos in enumerate(dialogue_positions):
        seg = segments[pos]
        result = extract_mention(
            dialogue_index=seg.index,
            segments=segments,
            context_before=context_before,
            context_after=context_after,
            pov_character=resolved_pov,
            model=model,
            prompt_version=prompt_version,
            previous_attributions=previous_attributions if use_rolling_context else None,
        )
        results.append(result)

        # Update rolling context
        if use_rolling_context:
            resolved = result.get("resolved_mention")
            if resolved:
                previous_attributions.append(
                    {
                        "index": seg.index,
                        "text": seg.text[:80],
                        "speaker": resolved,
                    }
                )
                previous_attributions = previous_attributions[-rolling_context_size:]

        if (count + 1) % 25 == 0:
            logger.info("Progress: %d/%d", count + 1, len(dialogue_positions))

    logger.info("Extraction complete: %d dialogues processed", len(results))
    return results
