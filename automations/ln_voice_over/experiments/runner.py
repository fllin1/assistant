"""Extraction runner: extract speaker mentions and save to extracted/.

Runs extraction on a batch of dialogues, saves a flat {index: speaker}
JSON file to the project's extracted/chapter_NN/ directory, along with
a config sidecar recording the parameters used.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ..config import PROJECTS_DIR
from ..extraction import ExtractionConfig, extract_chapter_mentions
from ..models import Chapter, SegmentType

logger = logging.getLogger(__name__)


def run_extraction_experiment(
    book_slug: str,
    chapter_id: str,
    config: ExtractionConfig,
    batch_start: int = 0,
    batch_size: int = 100,
) -> Path:
    """Run extraction on a batch and save results.

    Args:
        book_slug: Project directory name.
        chapter_id: Chapter identifier (e.g. "02", "04a").
        config: Extraction configuration (model, prompt, context, etc.).
        batch_start: Index into dialogue list to start from.
        batch_size: Number of dialogues to process.

    Returns:
        Path to the saved extraction file.
    """
    root = PROJECTS_DIR / book_slug
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

    # Also save config to project config/extractions/ for easy auditing
    config_extractions_dir = root / "config" / "extractions"
    config_extractions_dir.mkdir(parents=True, exist_ok=True)
    config_copy_path = config_extractions_dir / f"chapter_{chapter_id}_{base_name}.json"
    config_copy_path.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info("Extracted %d attributions → %s", len(flat), extracted_path)
    return extracted_path
