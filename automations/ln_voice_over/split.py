"""Stage 1: SPLIT — Split a volume text file into individual chapter files.

Reads a single .txt file containing an entire light novel volume and splits
it at chapter boundaries. Outputs one .txt file per chapter plus a
manifest.json with chapter metadata.

Chapter boundaries are detected by matching lines against configurable
regex patterns (see config.CHAPTER_PATTERNS).

NOTE: This module currently assumes a single .txt volume file as input.
If a second input format is needed (EPUB, PDF, web scrape), this is the
module to refactor into a Protocol + factory pattern — one implementation
per input format, all producing the same output (chapter files + manifest).
At that point, this module may also move from "transform" to a dedicated
"extract" step.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import CHAPTER_PATTERNS


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
    boundaries = []
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in patterns:
            if pattern.search(stripped):
                boundaries.append((i, stripped))
                break
    return boundaries


def _split_header_from_body(line: str) -> tuple[str, str]:
    """Separate the chapter header from body text on the same line.

    Returns:
        (header_portion, body_portion). body_portion is empty if no
        caps opener is detected.
    """
    # Find where the ALL-CAPS body opener starts. Our LN body text
    # opens with a stylized caps phrase like "WHEN I EVALUATE MYSELF",
    # "TUESDAY, NOVEMBER 9TH", or "FOUR O'CLOCK". We look for an
    # uppercase word of 2+ chars followed by more uppercase words,
    # allowing punctuation (commas, apostrophes) and single-letter words.
    # A caps "word" may contain internal apostrophes (O'CLOCK) and
    # trailing commas. We require the first word to be 2+ letters.
    caps_word = r"[A-Z]+(?:['\u2019][A-Z]+)*"
    m = re.search(rf"\s({caps_word}(?:,?\s+{caps_word}){{1,}})\b", line)
    if m:
        split_pos = m.start() + 1
        return line[:split_pos].strip(), line[split_pos:].strip()
    return line, ""


def _extract_title(header_line: str) -> str:
    """Extract a chapter title from a header line.

    Strips common prefixes like "Chapter 1:" or "Chapter 12 -".
    Assumes the header has already been separated from body text
    via _split_header_from_body().

    Falls back to the full line if no prefix pattern matches.
    """
    # With separator: "Chapter 1: Title" or "Chapter 1 - Title"
    m = re.match(r"^Chapter\s+\d+\s*[:\-\u2013\u2014]\s*(.+)$", header_line, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Without separator: "Chapter 1 Title"
    m = re.match(r"^Chapter\s+\d+\s+(.+)$", header_line, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return header_line


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
    if patterns is None:
        patterns = CHAPTER_PATTERNS

    text = source_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    boundaries = find_chapter_boundaries(text, patterns)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    if not boundaries:
        # No chapters detected — write the whole file as chapter_01
        filename = "chapter_01.txt"
        (output_dir / filename).write_text(text, encoding="utf-8")
        manifest.append({
            "number": 1,
            "title": source_path.stem,
            "file": filename,
            "pov_character": None,
        })
        return manifest

    # Content before the first chapter boundary → front matter
    first_boundary = boundaries[0][0]
    front_matter = "".join(lines[:first_boundary]).strip()
    if front_matter:
        filename = "chapter_00.txt"
        (output_dir / filename).write_text(front_matter + "\n", encoding="utf-8")
        manifest.append({
            "number": 0,
            "title": "Front Matter",
            "file": filename,
            "pov_character": None,
        })

    # Split at each boundary
    for i, (line_idx, header) in enumerate(boundaries):
        start = line_idx
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(lines)

        raw_chapter = "".join(lines[start:end]).strip()

        # The first line may have header + body mashed together.
        # Separate them so the output file has a clean header line.
        header_part, body_start = _split_header_from_body(header)
        if body_start:
            # Replace the mashed first line with header\n\nbody
            chapter_text = header_part + "\n\n" + body_start + raw_chapter[len(header):]
        else:
            chapter_text = raw_chapter

        chapter_num = i + 1
        filename = f"chapter_{chapter_num:02d}.txt"

        (output_dir / filename).write_text(chapter_text.strip() + "\n", encoding="utf-8")
        manifest.append({
            "number": chapter_num,
            "title": _extract_title(header_part),
            "file": filename,
            "pov_character": None,
        })

    return manifest


def write_manifest(chapters: list[dict], output_dir: Path) -> Path:
    """Write the chapter manifest to manifest.json.

    Args:
        chapters: List of manifest entries from split_volume().
        output_dir: Directory containing the chapter files.

    Returns:
        Path to the written manifest.json file.
    """
    path = output_dir / "manifest.json"
    path.write_text(
        json.dumps(chapters, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
