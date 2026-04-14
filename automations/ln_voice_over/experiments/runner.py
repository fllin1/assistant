"""Experiment runner for mention extraction.

Runs extraction on a batch of dialogues, saves config and results
to a timestamped experiment directory under the project.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from ..config import PROJECTS_DIR
from ..extraction import extract_chapter_mentions
from ..serialization import load_chapter

logger = logging.getLogger(__name__)


def _experiment_id(model: str, prompt_version: str, batch_start: int) -> str:
    """Generate a human-readable experiment ID."""
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    model_short = model.replace(":", "-").replace("/", "-")
    return f"{ts}_{model_short}_{prompt_version}_b{batch_start}"


def run_extraction_experiment(
    book_slug: str,
    chapter_num: int,
    model: str,
    prompt_version: str,
    context_before: int = 5,
    context_after: int = 5,
    batch_start: int = 0,
    batch_size: int = 100,
    pov_character: str | None = None,
    use_rolling_context: bool = False,
) -> Path:
    """Run extraction on a batch and save results.

    Args:
        book_slug: Project directory name.
        chapter_num: Chapter number to process.
        model: Ollama model tag (e.g. "gemma4:26b").
        prompt_version: Prompt version (e.g. "v1").
        context_before: Segments before the dialogue for context.
        context_after: Segments after the dialogue for context.
        batch_start: Index into dialogue list to start from.
        batch_size: Number of dialogues to process.
        pov_character: Override POV character.
        use_rolling_context: Pass recent attributions to each LLM call.

    Returns:
        Path to the experiment directory.
    """
    root = PROJECTS_DIR / book_slug
    parsed_path = root / "parsed" / f"chapter_{chapter_num:02d}.json"
    chapter = load_chapter(parsed_path)

    # Determine batch range
    batch_range = (batch_start, batch_start + batch_size)

    # Count total dialogues for logging
    from ..models import SegmentType

    total_dialogues = sum(1 for s in chapter.segments if s.segment_type == SegmentType.DIALOGUE)
    actual_end = min(batch_start + batch_size, total_dialogues)
    logger.info(
        "Running experiment: %s ch%d [%d:%d]/%d, model=%s, prompt=%s",
        book_slug,
        chapter_num,
        batch_start,
        actual_end,
        total_dialogues,
        model,
        prompt_version,
    )

    # Run extraction
    results = extract_chapter_mentions(
        chapter,
        model=model,
        context_before=context_before,
        context_after=context_after,
        prompt_version=prompt_version,
        pov_character=pov_character,
        batch_range=batch_range,
        use_rolling_context=use_rolling_context,
    )

    # Save results
    exp_id = _experiment_id(model, prompt_version, batch_start)
    exp_dir = root / "experiments" / "extraction" / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "book_slug": book_slug,
        "chapter": chapter_num,
        "model": model,
        "prompt_version": prompt_version,
        "context_before": context_before,
        "context_after": context_after,
        "use_rolling_context": use_rolling_context,
        "batch_start": batch_start,
        "batch_size": batch_size,
        "actual_count": len(results),
        "total_dialogues": total_dialogues,
        "pov_character": pov_character or chapter.pov_character,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    (exp_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (exp_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info("Experiment saved to %s", exp_dir)
    return exp_dir
