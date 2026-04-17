"""Stage 1: SPLIT — Split a volume into individual chapter files.

Reads from a project's `source/` folder. Two input formats are supported:
- `book.json`: Pre-structured from the /setup-book skill. Chapters already
  split with titles; illustrations extracted to a manifest.
- `*.txt`: Raw volume text. Chapter boundaries detected by regex patterns.

Both formats produce the same output: one .txt file per chapter plus a
manifest.json with chapter metadata. Downstream stages (clean, parse)
are format-agnostic.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .config import CHAPTER_PATTERNS

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def split_volume(
    source_path: Path,
    output_dir: Path,
    patterns: list[re.Pattern[str]] | None = None,
    illustrations_dir: Path | None = None,
) -> list[dict]:
    """Split a volume file into per-chapter text files.

    Dispatches to the appropriate strategy based on file extension.

    Args:
        source_path: Path to the volume file (.txt or .json).
        output_dir: Directory to write chapter files into (created if needed).
        patterns: Chapter boundary patterns (only used for .txt input).
        illustrations_dir: Directory to write illustration images and manifest
            (only used for .json input). If None, defaults to
            source_path.parent.parent / "illustrations".

    Returns:
        List of manifest entries, each a dict with keys:
        number (int), title (str), file (str), pov_character (None).
    """
    if source_path.suffix == ".json":
        return _split_from_json(source_path, output_dir, illustrations_dir)
    return _split_from_txt(source_path, output_dir, patterns)


def write_manifest(chapters: list[dict], output_dir: Path) -> Path:
    """Write the chapter manifest to manifest.json."""
    path = output_dir / "manifest.json"
    path.write_text(
        json.dumps(chapters, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Strategy: .txt (regex-based splitting)
# ---------------------------------------------------------------------------


def find_chapter_boundaries(text: str, patterns: list[re.Pattern[str]]) -> list[tuple[int, str]]:
    """Find line indices where new chapters begin.

    Returns:
        List of (line_index, matched_line_text) tuples, sorted by position.
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
    """Separate the chapter header from body text on the same line."""
    caps_word = r"[A-Z]+(?:['\u2019][A-Z]+)*"
    m = re.search(rf"\s({caps_word}(?:,?\s+{caps_word}){{1,}})\b", line)
    if m:
        split_pos = m.start() + 1
        return line[:split_pos].strip(), line[split_pos:].strip()
    return line, ""


def _extract_title(header_line: str) -> str:
    """Extract a chapter title from a header line."""
    m = re.match(r"^Chapter\s+\d+\s*[:\-\u2013\u2014]\s*(.+)$", header_line, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.match(r"^Chapter\s+\d+\s+(.+)$", header_line, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return header_line


def _split_from_txt(
    source_path: Path,
    output_dir: Path,
    patterns: list[re.Pattern[str]] | None = None,
) -> list[dict]:
    """Split a .txt volume file using regex-based chapter detection."""
    if patterns is None:
        patterns = CHAPTER_PATTERNS

    text = source_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    boundaries = find_chapter_boundaries(text, patterns)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    if not boundaries:
        filename = "chapter_01.txt"
        (output_dir / filename).write_text(text, encoding="utf-8")
        manifest.append(
            {
                "number": 1,
                "title": source_path.stem,
                "file": filename,
                "pov_character": None,
            }
        )
        return manifest

    # Content before the first chapter boundary → front matter
    first_boundary = boundaries[0][0]
    front_matter = "".join(lines[:first_boundary]).strip()
    if front_matter:
        filename = "chapter_00.txt"
        (output_dir / filename).write_text(front_matter + "\n", encoding="utf-8")
        manifest.append(
            {
                "number": 0,
                "title": "Front Matter",
                "file": filename,
                "pov_character": None,
            }
        )

    for i, (line_idx, header) in enumerate(boundaries):
        start = line_idx
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(lines)

        raw_chapter = "".join(lines[start:end]).strip()

        header_part, body_start = _split_header_from_body(header)
        if body_start:
            chapter_text = header_part + "\n\n" + body_start + raw_chapter[len(header) :]
        else:
            chapter_text = raw_chapter

        chapter_num = i + 1
        filename = f"chapter_{chapter_num:02d}.txt"

        (output_dir / filename).write_text(chapter_text.strip() + "\n", encoding="utf-8")
        manifest.append(
            {
                "number": chapter_num,
                "title": _extract_title(header_part),
                "file": filename,
                "pov_character": None,
            }
        )

    return manifest


# ---------------------------------------------------------------------------
# Strategy: .json (pre-structured book from /extract-book skill)
# ---------------------------------------------------------------------------


def _split_from_json(
    source_path: Path,
    output_dir: Path,
    illustrations_dir: Path | None = None,
) -> list[dict]:
    """Split a pre-structured book JSON into chapter files.

    The JSON is expected to have:
    - chapters: list of {title, text, start_page?, illustrations?}
    - front_matter?: {illustrations: [{page, image_path, ...}]}

    Produces the same output as _split_from_txt: chapter .txt files + manifest.
    Also copies illustrations to illustrations_dir if present.
    """
    data = json.loads(source_path.read_text(encoding="utf-8"))
    source_dir = source_path.parent

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    chapters = data.get("chapters", [])
    for i, chapter in enumerate(chapters):
        chapter_num = i + 1
        filename = f"chapter_{chapter_num:02d}.txt"
        text = chapter.get("text", "")

        (output_dir / filename).write_text(text.strip() + "\n", encoding="utf-8")
        manifest.append(
            {
                "number": chapter_num,
                "title": chapter.get("title", f"Chapter {chapter_num}"),
                "file": filename,
                "pov_character": chapter.get("pov_character"),
            }
        )

    # Handle illustrations
    if illustrations_dir is None:
        illustrations_dir = source_dir.parent / "illustrations"

    all_illustrations = []

    # Front matter illustrations
    front_matter = data.get("front_matter", {})
    for ill in front_matter.get("illustrations", []):
        all_illustrations.append({**ill, "position": "front_matter"})

    # Per-chapter illustrations
    for i, chapter in enumerate(chapters):
        for ill in chapter.get("illustrations", []):
            all_illustrations.append({**ill, "position": f"chapter_{i + 1:02d}"})

    if all_illustrations:
        images_dir = illustrations_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        for ill in all_illustrations:
            src = source_dir / ill.get("image_path", "")
            if src.exists():
                dest_name = f"ill_{ill.get('page', 0):03d}.png"
                dest = images_dir / dest_name
                if not dest.exists():
                    shutil.copy2(src, dest)
                ill["file"] = f"images/{dest_name}"

        ill_manifest = {
            "book_slug": data.get("book_slug", source_path.parent.parent.name),
            "source": data.get("source", {}),
            "illustrations": all_illustrations,
        }
        illustrations_dir.mkdir(parents=True, exist_ok=True)
        (illustrations_dir / "manifest.json").write_text(
            json.dumps(ill_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return manifest
