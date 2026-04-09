"""Stage 1: SPLIT — Split a volume text file into individual chapter files.

Reads a single .txt file containing an entire light novel volume and splits
it at chapter boundaries. Outputs one .txt file per chapter plus a
manifest.json with chapter metadata.

Chapter boundaries are detected by matching lines against configurable
regex patterns (see config.CHAPTER_PATTERNS).
"""

from __future__ import annotations

import re
from pathlib import Path


def find_chapter_boundaries(
    text: str, patterns: list[re.Pattern[str]]
) -> list[tuple[int, str]]:
    """Find line indices where new chapters begin.

    Args:
        text: Full volume text.
        patterns: Compiled regex patterns that mark chapter starts.

    Returns:
        List of (line_index, matched_line_text) tuples, sorted by position.
        The line_index is 0-based into text.splitlines().
    """
    ...


def split_volume(
    source_path: Path,
    output_dir: Path,
    patterns: list[re.Pattern[str]] | None = None,
) -> list[dict]:
    """Split a volume file into per-chapter text files.

    Args:
        source_path: Path to the raw volume .txt file.
        output_dir: Directory to write chapter files into (created if needed).
        patterns: Chapter boundary patterns. Defaults to config.CHAPTER_PATTERNS.

    Returns:
        List of manifest entries, each a dict with keys:
        number (int), title (str), file (str), pov_character (None).

    The chapter files are named chapter_01.txt, chapter_02.txt, etc.
    Content before the first chapter boundary is saved as chapter_00.txt
    (front matter) if non-empty.
    """
    ...


def write_manifest(chapters: list[dict], output_dir: Path) -> Path:
    """Write the chapter manifest to manifest.json.

    Args:
        chapters: List of manifest entries from split_volume().
        output_dir: Directory containing the chapter files.

    Returns:
        Path to the written manifest.json file.
    """
    ...
