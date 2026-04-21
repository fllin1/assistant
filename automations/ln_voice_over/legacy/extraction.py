"""Step 1: Speaker mention extraction from narration context.

Extracts WHO is speaking each dialogue segment by analyzing surrounding
narration for speech tags, pronouns, and conversational flow.

Two modes:
- Fast (default): LLM returns just a speaker name.
- Verbose: LLM returns speaker + reasoning JSON, useful for debugging.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..llm import LLMClient
from ..models import Chapter, Segment, SegmentType
from ..project import resolve_volume

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@dataclass(frozen=True)
class ExtractionConfig:
    """Configuration for a mention extraction run."""

    model: str = "gemma4:26b"
    context_before: int = 10
    context_after: int = 5
    pov_character: str | None = None
    use_rolling_context: bool = False
    rolling_context_size: int = 10
    fast: bool = True

    def build_system_prompt(self) -> str:
        """Read and format the system prompt template."""
        filename = "extraction_fast.txt" if self.fast else "extraction_v2.txt"
        template = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        return template.format(pov_character=self.pov_character or "unknown narrator")


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


def _parse_verbose_response(response: str) -> dict | None:
    """Parse the LLM's verbose JSON response into speaker + reasoning."""
    text = response.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        text_lines = text.split("\n")
        text_lines = [line for line in text_lines if not line.strip().startswith("```")]
        text = "\n".join(text_lines).strip()

    json_start = text.find("{")
    json_end = text.rfind("}")
    if json_start == -1 or json_end == -1:
        logger.warning("No JSON object found in response: %s", text[:200])
        return None

    try:
        data = json.loads(text[json_start : json_end + 1])
    except json.JSONDecodeError:
        logger.warning("Failed to parse verbose response: %s", text[:200])
        return None

    return {
        "speaker": data.get("speaker") or data.get("resolved_mention"),
        "reasoning": data.get("reasoning", ""),
    }


def extract_mention(
    dialogue_index: int,
    segments: list[Segment],
    client: LLMClient,
    system_prompt: str,
    config: ExtractionConfig,
    previous_attributions: list[dict] | None = None,
) -> dict:
    """Extract speaker mention for a single dialogue segment."""
    user_prompt = _build_user_prompt(dialogue_index, segments, config, previous_attributions)
    raw_response = client.chat(system_prompt, user_prompt)

    if config.fast:
        name = raw_response.strip().strip('"').strip("'")
        return {
            "index": dialogue_index,
            "speaker": name,
            "reasoning": "",
            "model": config.model,
        }

    parsed = _parse_verbose_response(raw_response)
    if parsed is None:
        return {
            "index": dialogue_index,
            "speaker": None,
            "reasoning": "Failed to parse LLM response",
            "model": config.model,
        }

    return {
        "index": dialogue_index,
        "speaker": parsed["speaker"],
        "reasoning": parsed["reasoning"],
        "model": config.model,
    }


def extract_chapter_mentions(
    chapter: Chapter,
    config: ExtractionConfig,
    batch_range: tuple[int, int] | None = None,
) -> list[dict]:
    """Run mention extraction on all (or a batch of) dialogues in a chapter.

    Creates an LLMClient once and reuses it across all dialogue extractions.

    Args:
        chapter: Parsed chapter with segments.
        config: Extraction configuration.
        batch_range: Optional (start, end) slice into dialogue indices.

    Returns:
        List of extraction dicts, one per dialogue segment.
    """
    client = LLMClient(config.model)
    system_prompt = config.build_system_prompt()

    segments = list(chapter.segments)
    dialogue_positions = [
        i for i, s in enumerate(segments) if s.segment_type == SegmentType.DIALOGUE
    ]

    if batch_range:
        start, end = batch_range
        dialogue_positions = dialogue_positions[start:end]

    mode = "fast" if config.fast else "verbose"
    logger.info(
        "Extracting mentions: %d dialogues, model=%s, mode=%s, context=-%d/+%d, rolling=%s",
        len(dialogue_positions),
        config.model,
        mode,
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
            client=client,
            system_prompt=system_prompt,
            config=config,
            previous_attributions=previous_attributions if config.use_rolling_context else None,
        )
        results.append(result)

        if (count + 1) % 25 == 0:
            logger.info("Progress: %d/%d", count + 1, len(dialogue_positions))

        # Update rolling context
        if not config.use_rolling_context:
            continue

        speaker = result.get("speaker")
        if speaker:
            previous_attributions.append(
                {
                    "index": seg.index,
                    "text": seg.text[:80],
                    "speaker": speaker,
                }
            )
            previous_attributions = previous_attributions[-config.rolling_context_size :]

    logger.info("Extraction complete: %d dialogues processed", len(results))
    return results


def run_extraction(
    book_slug: str,
    chapter_id: str,
    config: ExtractionConfig,
    batch_start: int = 0,
    batch_size: int = 100,
) -> Path:
    """Run extraction on a chapter and save results + config sidecar.

    Loads the parsed chapter, runs `extract_chapter_mentions` on the given
    dialogue slice, and writes a flat {index: speaker} JSON to
    `extracted/chapter_NN/<model>_<mode>_<date>.json`. The config used
    is saved alongside and copied to `config/extractions/` for auditing.

    Args:
        book_slug: Project directory name.
        chapter_id: Chapter identifier (e.g. "02", "04a").
        config: Extraction configuration.
        batch_start: Index into the dialogue list to start from.
        batch_size: Number of dialogues to process.

    Args:
        book_slug: `<series>/<volume>` slug or legacy flat slug.

    Returns:
        Path to the saved extraction file.
    """
    resolved = resolve_volume(book_slug)
    root = resolved.volume_path
    parsed_path = root / "parsed" / f"chapter_{chapter_id}.json"
    chapter = Chapter.load(parsed_path)

    batch_range = (batch_start, batch_start + batch_size)

    total_dialogues = sum(1 for s in chapter.segments if s.segment_type == SegmentType.DIALOGUE)
    actual_end = min(batch_start + batch_size, total_dialogues)
    logger.info(
        "Running extraction: %s ch%s [%d:%d]/%d, model=%s",
        book_slug,
        chapter_id,
        batch_start,
        actual_end,
        total_dialogues,
        config.model,
    )

    results = extract_chapter_mentions(chapter, config, batch_range=batch_range)

    # Build flat {index: speaker} dict
    flat = {str(r["index"]): r["speaker"] for r in results if r.get("speaker")}

    # File naming
    model_short = config.model.replace(":", "-").replace("/", "-")
    mode = "fast" if config.fast else "verbose"
    ts = datetime.now(UTC).strftime("%Y%m%d")
    base_name = f"{model_short}_{mode}_{ts}"

    # Save extraction results
    extracted_dir = root / "extracted" / f"chapter_{chapter_id}"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = extracted_dir / f"{base_name}.json"
    extracted_path.write_text(json.dumps(flat, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save config sidecar alongside extraction
    config_data = {
        **asdict(config),
        "book_slug": book_slug,
        "chapter": chapter_id,
        "batch_start": batch_start,
        "batch_size": batch_size,
        "actual_dialogues": len(flat),
        "total_dialogues": total_dialogues,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    config_path = extracted_dir / f"{base_name}_config.json"
    config_path.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Extracted %d attributions → %s", len(flat), extracted_path)
    return extracted_path
