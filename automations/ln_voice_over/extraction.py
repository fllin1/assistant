"""Step 1: Speaker mention extraction from narration context.

Extracts WHO is speaking each dialogue segment by analyzing surrounding
narration for speech tags, pronouns, and conversational flow. Does NOT
resolve mentions to canonical registry names — that's Step 2.

Each dialogue gets an LLM call with configurable context window.
The LLM returns the raw mention (name/pronoun/null), its best guess at
the character, the narration source, and brief reasoning.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .llm import call_llm
from .models import Chapter, Segment, SegmentType

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Pronouns for mention_type classification
_PRONOUNS = {"he", "she", "they", "her", "him", "his"}
_FIRST_PERSON = {"i", "me", "my"}


@dataclass(frozen=True)
class ExtractionConfig:
    """Configuration for a mention extraction run.

    Bundles all experiment parameters so they're passed as a single
    object instead of threaded through every function signature.
    """

    model: str = "gemma4:26b"
    prompt_version: str = "v1"
    context_before: int = 5
    context_after: int = 5
    pov_character: str | None = None
    use_rolling_context: bool = False
    rolling_context_size: int = 5

    @property
    def system_prompt(self) -> str:
        """Load and format the system prompt template. Cached per instance."""
        if not hasattr(self, "_cached_system_prompt"):
            template = (PROMPTS_DIR / f"extraction_{self.prompt_version}.txt").read_text(
                encoding="utf-8"
            )
            prompt = template.format(pov_character=self.pov_character or "unknown narrator")
            # Frozen dataclass — use object.__setattr__ for caching
            object.__setattr__(self, "_cached_system_prompt", prompt)
        return self._cached_system_prompt  # type: ignore[attr-defined]


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


def _build_user_prompt(
    target_index: int,
    segments: list[Segment],
    config: ExtractionConfig,
    previous_attributions: list[dict] | None = None,
) -> str:
    """Build the user prompt with context segments around the target dialogue."""
    pos = next(i for i, s in enumerate(segments) if s.index == target_index)

    start = max(0, pos - config.context_before)
    end = min(len(segments), pos + config.context_after + 1)
    context = segments[start:end]

    lines = []
    if config.pov_character:
        lines.append(f"Narrator: {config.pov_character}")
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
        text_lines = text.split("\n")
        text_lines = [line for line in text_lines if not line.strip().startswith("```")]
        text = "\n".join(text_lines).strip()

    # Extract JSON object from potentially wrapped text
    json_start = text.find("{")
    json_end = text.rfind("}")
    if json_start == -1 or json_end == -1:
        logger.warning("No JSON object found in response: %s", text[:200])
        return None

    try:
        data = json.loads(text[json_start : json_end + 1])
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


def _enrich_result(
    parsed: dict,
    dialogue_index: int,
    segments: list[Segment],
    model: str,
) -> dict:
    """Add derived fields and validate the raw LLM result.

    Adds: index, mention_position, model, _source_valid.
    Overrides mention_type with deterministic classification.
    """
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

    # Validate that mention_source_index actually contains raw_mention
    raw = parsed.get("raw_mention")
    if source_idx is not None and raw is not None:
        source_seg = next((s for s in segments if s.index == source_idx), None)
        if source_seg and raw.lower() in source_seg.text.lower():
            parsed["_source_valid"] = True
        else:
            parsed["_source_valid"] = False
            if source_seg:
                logger.debug(
                    "Source index %d does not contain '%s': %s",
                    source_idx,
                    raw,
                    source_seg.text[:80],
                )

    return parsed


_EMPTY_RESULT = {
    "raw_mention": None,
    "resolved_mention": None,
    "mention_source_index": None,
    "mention_type": "none",
    "reasoning": "Failed to parse LLM response",
}


def extract_mention(
    dialogue_index: int,
    segments: list[Segment],
    config: ExtractionConfig,
    previous_attributions: list[dict] | None = None,
) -> dict:
    """Extract speaker mention for a single dialogue segment.

    Args:
        dialogue_index: The segment index of the target dialogue.
        segments: All segments in the chapter.
        config: Extraction configuration.
        previous_attributions: Recent attributions for conversational context.

    Returns:
        Enriched dict with index, raw_mention, resolved_mention,
        mention_source_index, mention_position, mention_type,
        reasoning, model, _source_valid.
    """
    user_prompt = _build_user_prompt(dialogue_index, segments, config, previous_attributions)
    raw_response = call_llm(config.system_prompt, user_prompt, config.model)
    parsed = parse_extraction_response(raw_response) or dict(_EMPTY_RESULT)

    return _enrich_result(parsed, dialogue_index, segments, config.model)


def extract_chapter_mentions(
    chapter: Chapter,
    config: ExtractionConfig,
    batch_range: tuple[int, int] | None = None,
) -> list[dict]:
    """Run mention extraction on all (or a batch of) dialogues in a chapter.

    Args:
        chapter: Parsed chapter with segments.
        config: Extraction configuration.
        batch_range: Optional (start, end) slice into dialogue indices.

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

    logger.info(
        "Extracting mentions: %d dialogues, model=%s, prompt=%s, context=-%d/+%d, rolling=%s",
        len(dialogue_positions),
        config.model,
        config.prompt_version,
        config.context_before,
        config.context_after,
        config.use_rolling_context,
    )

    results = []
    previous_attributions: list[dict] = []

    for count, pos in enumerate(dialogue_positions):
        seg = segments[pos]
        result = extract_mention(
            dialogue_index=seg.index,
            segments=segments,
            config=config,
            previous_attributions=previous_attributions if config.use_rolling_context else None,
        )
        results.append(result)

        # Update rolling context
        if config.use_rolling_context:
            resolved = result.get("resolved_mention")
            if resolved:
                previous_attributions.append(
                    {
                        "index": seg.index,
                        "text": seg.text[:80],
                        "speaker": resolved,
                    }
                )
                previous_attributions = previous_attributions[-config.rolling_context_size :]

        if (count + 1) % 25 == 0:
            logger.info("Progress: %d/%d", count + 1, len(dialogue_positions))

    logger.info("Extraction complete: %d dialogues processed", len(results))
    return results
