"""LLM prompt templates for speaker attribution.

Builds structured prompts for the attribution LLM, including the character
registry, previous context window, and current segments to attribute.

The LLM is asked to return a JSON array mapping segment indices to
{speaker, confidence} pairs. Only dialogue segments need attribution —
narration is always the narrator/POV character.
"""

from __future__ import annotations

import json
import logging

from .models import CharacterRegistry, Segment

logger = logging.getLogger(__name__)


def build_system_prompt() -> str:
    """Return the system prompt for the attribution LLM.

    Instructs the LLM to act as a literary analyst, explains the
    expected input/output format, and sets rules for handling
    ambiguous cases (unknown speakers, group conversations).
    """
    return """\
You are a literary analyst specializing in light novel dialogue attribution.

You will receive:
1. A character registry with canonical names and aliases.
2. A list of text segments (narration and dialogue interleaved).

Your task: for each DIALOGUE segment, determine who is speaking.

Rules:
- Use canonical character names from the registry exactly as written.
- ALWAYS check narration BEFORE and AFTER each dialogue segment for attribution \
tags (e.g. "asked Ike", "she said", "Horikita replied"). The speaker's name or \
alias often appears in the narration immediately following the dialogue.
- Match character aliases case-insensitively to their canonical name.
- Confidence is a float from 0.0 to 1.0 reflecting how certain you are.
- If the speaker is ambiguous, use your best guess with lower confidence.
- If completely unknown, use "Unknown" with confidence 0.0.
- Do NOT attribute narration segments — only dialogue.

Return ONLY a JSON array. No markdown, no commentary, no explanation.
Each element: {"index": <int>, "speaker": "<name>", "confidence": <float>}"""


def build_attribution_prompt(
    segments: list[Segment],
    registry: CharacterRegistry,
    previous_attributions: list[dict] | None = None,
) -> str:
    """Build the user prompt for a single attribution window.

    Args:
        segments: The segments in this window to attribute.
        registry: Character registry with names, aliases, genders.
        previous_attributions: Last N attributions from the previous
            window, providing continuity context. Each dict has keys:
            index, segment_type, text, speaker.

    Returns:
        The formatted user prompt string. Includes the character list,
        previous context, and segments as JSON for the LLM to process.
    """
    parts = []

    # Character registry
    parts.append("# Characters\n")
    for char in registry.characters:
        aliases = ", ".join(char.aliases) if char.aliases else "none"
        parts.append(f"- {char.name} (aliases: {aliases}, {char.gender}, {char.role})")
        if char.description:
            parts.append(f"  {char.description}")
    parts.append("")

    # Previous context for continuity
    if previous_attributions:
        parts.append("# Previous context (from prior window)\n")
        for attr in previous_attributions:
            parts.append(
                f"- [{attr['index']}] {attr['segment_type']}: "
                f"{attr['text'][:80]}... → {attr['speaker']}"
            )
        parts.append("")

    # Current segments
    parts.append("# Segments to process\n")
    seg_list = []
    for seg in segments:
        seg_list.append(
            {
                "index": seg.index,
                "type": seg.segment_type.value,
                "text": seg.text[:300],
            }
        )
    parts.append(json.dumps(seg_list, indent=2, ensure_ascii=False))
    parts.append("")
    parts.append("Attribute the dialogue segments. Return ONLY a JSON array.")

    return "\n".join(parts)


def build_single_attribution_prompt(
    context_segments: list[Segment],
    target_index: int,
    registry: CharacterRegistry,
    previous_attributions: list[dict] | None = None,
) -> str:
    """Build a prompt to attribute a single dialogue segment.

    Args:
        context_segments: Small window of segments around the target.
        target_index: The segment index of the dialogue to attribute.
        registry: Character registry with names and aliases.
        previous_attributions: Recent attributions for conversational
            continuity. Each dict has keys: index, text, speaker.
    """
    parts = []

    parts.append("# Characters\n")
    for char in registry.characters:
        aliases = ", ".join(char.aliases) if char.aliases else "none"
        parts.append(f"- {char.name} (aliases: {aliases})")
    parts.append("")

    if previous_attributions:
        parts.append("# Recent speakers\n")
        for attr in previous_attributions:
            parts.append(f'- [{attr["index"]}] "{attr["text"][:60]}..." → {attr["speaker"]}')
        parts.append("")

    parts.append("# Context\n")
    for seg in context_segments:
        marker = " <<<< ATTRIBUTE THIS" if seg.index == target_index else ""
        parts.append(f"[{seg.segment_type.value}] {seg.text[:300]}{marker}")
    parts.append("")
    parts.append(
        f"Who is speaking the dialogue segment at index {target_index}? "
        "Return ONLY a JSON object: "
        '{"index": <int>, "speaker": "<name>", "confidence": <float>}'
    )

    return "\n".join(parts)


def parse_attribution_response(response: str) -> list[dict]:
    """Parse the LLM's attribution response into structured data.

    Extracts the JSON array from the LLM response. Handles cases where
    the LLM wraps the JSON in markdown code fences or adds commentary.

    Args:
        response: Raw LLM response text.

    Returns:
        List of dicts, each with keys: index (int), speaker (str),
        confidence (float). Returns empty list if parsing fails.
    """
    text = response.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse attribution response: %s", text[:200])
        return []

    # Handle single object (from per-dialogue mode) — wrap in list
    if isinstance(data, dict):
        # Check if it's a direct attribution object
        if "speaker" in data:
            data = [data]
        else:
            # Object wrapper (e.g. {"attributions": [...]})
            for key in ("attributions", "results", "data"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                logger.warning("Unexpected response format: %s", text[:200])
                return []

    if not isinstance(data, list):
        return []

    results = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if "index" not in entry or "speaker" not in entry:
            continue
        confidence = float(entry.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        results.append(
            {
                "index": int(entry["index"]),
                "speaker": str(entry["speaker"]),
                "confidence": confidence,
            }
        )

    return results
