"""Stage 2: CLEAN — Remove artifacts from chapter text files.

Strips watermarks, page numbers, and normalizes whitespace while preserving
scene breaks and meaningful formatting. Operates on individual chapter files.

All pattern matching is configurable via config.py constants.
"""

from __future__ import annotations

import re
from pathlib import Path


def is_watermark_line(line: str, patterns: list[str]) -> bool:
    """Check if a line contains any watermark substring.

    Args:
        line: A single line of text.
        patterns: Watermark substrings to match against.

    Returns:
        True if the line should be removed.
    """
    ...


def is_page_number(line: str, patterns: list[re.Pattern[str]]) -> bool:
    """Check if a line is a standalone page number.

    Args:
        line: A single line of text.
        patterns: Compiled regex patterns for page numbers.
    """
    ...


def is_scene_break(line: str, patterns: list[re.Pattern[str]]) -> bool:
    """Check if a line is a scene break marker.

    Scene breaks are preserved during cleaning — they become
    SCENE_BREAK segments during parsing.
    """
    ...


def collapse_blank_lines(text: str, max_consecutive: int = 2) -> str:
    """Collapse runs of blank lines exceeding max_consecutive.

    Preserves intentional spacing while removing excessive gaps.
    """
    ...


def clean_chapter(source_path: Path, output_path: Path) -> Path:
    """Clean a single chapter file and write the result.

    Applies all cleaning rules in order:
    1. Remove watermark lines
    2. Remove page number lines
    3. Trim trailing whitespace per line
    4. Collapse excessive blank lines

    Args:
        source_path: Path to the chapter file from the chapters/ directory.
        output_path: Path to write the cleaned file.

    Returns:
        Path to the written cleaned file.
    """
    ...
