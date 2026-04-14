"""Experiment runner for mention extraction.

Runs extraction on a batch of dialogues, saves config and results
to a timestamped experiment directory under the project.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ..config import PROJECTS_DIR
from ..extraction import ExtractionConfig, extract_chapter_mentions
from ..models import SegmentType
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
    config: ExtractionConfig,
    batch_start: int = 0,
    batch_size: int = 100,
) -> Path:
    """Run extraction on a batch and save results.

    Args:
        book_slug: Project directory name.
        chapter_num: Chapter number to process.
        config: Extraction configuration (model, prompt, context, etc.).
        batch_start: Index into dialogue list to start from.
        batch_size: Number of dialogues to process.

    Returns:
        Path to the experiment directory.
    """
    root = PROJECTS_DIR / book_slug
    parsed_path = root / "parsed" / f"chapter_{chapter_num:02d}.json"
    chapter = load_chapter(parsed_path)

    batch_range = (batch_start, batch_start + batch_size)

    total_dialogues = sum(1 for s in chapter.segments if s.segment_type == SegmentType.DIALOGUE)
    actual_end = min(batch_start + batch_size, total_dialogues)
    logger.info(
        "Running experiment: %s ch%d [%d:%d]/%d, model=%s, prompt=%s",
        book_slug,
        chapter_num,
        batch_start,
        actual_end,
        total_dialogues,
        config.model,
        config.prompt_version,
    )

    results = extract_chapter_mentions(chapter, config, batch_range=batch_range)

    # Save results
    exp_id = _experiment_id(config.model, config.prompt_version, batch_start)
    exp_dir = root / "experiments" / "extraction" / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)

    saved_config = {
        **asdict(config),
        "book_slug": book_slug,
        "chapter": chapter_num,
        "batch_start": batch_start,
        "batch_size": batch_size,
        "actual_count": len(results),
        "total_dialogues": total_dialogues,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    (exp_dir / "config.json").write_text(
        json.dumps(saved_config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (exp_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info("Experiment saved to %s", exp_dir)
    return exp_dir
