"""LLM prompt templates for speaker attribution.

Builds structured prompts for the attribution LLM, including the character
registry, previous context window, and current segments to attribute.

The LLM is asked to return a JSON array mapping segment indices to
{speaker, confidence} pairs. Only dialogue and inner_thought segments
need attribution — narration is always the narrator/POV character.
"""

from __future__ import annotations

from .models import CharacterRegistry, Segment


def build_system_prompt() -> str:
    """Return the system prompt for the attribution LLM.

    Instructs the LLM to act as a literary analyst, explains the
    expected input/output format, and sets rules for handling
    ambiguous cases (unknown speakers, group conversations).
    """
    ...


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
    ...


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
    ...
