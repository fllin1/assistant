"""Stage 2: CLEAN — Remove artifacts from chapter text files.

Strips watermarks, page numbers, and normalizes whitespace while preserving
scene breaks and meaningful formatting. Operates on individual chapter files.

All pattern matching is configurable via config.py constants.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import (
    INLINE_WATERMARK_PATTERNS,
    MAX_CONSECUTIVE_BLANK_LINES,
    PAGE_NUMBER_PATTERNS,
    SCENE_BREAK_PATTERNS,
    WATERMARK_PATTERNS,
)


def _strip_inline_watermarks(line: str, patterns: list[re.Pattern[str]]) -> str:
    for p in patterns:
        line = p.sub("", line)
    return line


def _is_watermark_line(line: str, patterns: list[str]) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(p in stripped for p in patterns)


def _is_page_number(line: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(line) for p in patterns)


def _is_scene_break(line: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(line) for p in patterns)


def collapse_blank_lines(text: str, max_consecutive: int = 2) -> str:
    """Collapse runs of blank lines exceeding max_consecutive.

    Preserves intentional spacing while removing excessive gaps.
    """
    lines = text.split("\n")
    result = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= max_consecutive:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)
    return "\n".join(result)


def clean_chapter(source_path: Path, output_path: Path) -> Path:
    """Clean a single chapter file and write the result.

    Applies all cleaning rules in order:
    1. Preserve scene break lines
    2. Remove watermark lines
    3. Remove page number lines
    4. Trim trailing whitespace per line
    5. Collapse excessive blank lines

    Args:
        source_path: Path to the chapter file from the chapters/ directory.
        output_path: Path to write the cleaned file.

    Returns:
        Path to the written cleaned file.
    """
    text = source_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    cleaned = []
    for line in lines:
        # Scene breaks are always preserved
        if _is_scene_break(line, SCENE_BREAK_PATTERNS):
            cleaned.append(line.rstrip())
            continue
        # Strip inline watermark suffixes (e.g., "Page 1 Goldenagato | mp4directs.com")
        line = _strip_inline_watermarks(line, INLINE_WATERMARK_PATTERNS)
        # Remove lines that are nothing but a watermark
        if _is_watermark_line(line, WATERMARK_PATTERNS):
            continue
        if _is_page_number(line, PAGE_NUMBER_PATTERNS):
            continue
        cleaned.append(line.rstrip())

    result = "\n".join(cleaned)
    result = collapse_blank_lines(result, MAX_CONSECUTIVE_BLANK_LINES)
    result = result.strip() + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")
    return output_path


def clean_all(chapters_dir: Path, output_dir: Path) -> list[Path]:
    """Clean all chapter files from chapters_dir, writing results to output_dir.

    Processes .txt files in sorted order. Non-.txt files (like manifest.json)
    are skipped.

    Args:
        chapters_dir: Path to the chapters/ directory (Stage 1 output).
        output_dir: Path to the cleaned/ directory.

    Returns:
        List of paths to the written cleaned files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for source in sorted(chapters_dir.glob("*.txt")):
        output_path = output_dir / source.name
        clean_chapter(source, output_path)
        results.append(output_path)
    return results
