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
import logging
import re
import shutil
from pathlib import Path

from .config import CHAPTER_PATTERNS, SUBCHAPTER_PATTERN

logger = logging.getLogger(__name__)


def _subdivide_by_subchapter(
    chapter_text: str, chapter_number: int
) -> list[tuple[int | None, str]]:
    """Scan a main chapter's body for bare `N.M` sub-chapter markers.

    Returns a list of `(subchapter_idx, text_slice)` tuples. When no valid
    markers are present, returns a single-item list `[(None, chapter_text)]`
    signalling "no subdivision" to the caller.

    Validity rules (all must hold for subdivision to apply):
      1. At least two markers in the chapter.
      2. Each marker's major number matches `chapter_number` (a stray `4.2`
         inside chapter 7 is ignored as narrative text).
      3. Minor numbers are strictly increasing starting from 1.

    Content before the first marker is prepended to sub-chapter 1 — common in
    chapters that open with a lead-in narration before the first `N.1` break.
    """
    lines = chapter_text.splitlines(keepends=True)
    markers: list[tuple[int, int]] = []  # (line_idx, minor)
    for i, line in enumerate(lines):
        m = SUBCHAPTER_PATTERN.match(line)
        if not m:
            continue
        major, minor = int(m.group(1)), int(m.group(2))
        if major != chapter_number:
            continue
        markers.append((i, minor))

    if len(markers) < 2:
        return [(None, chapter_text)]

    expected = list(range(1, len(markers) + 1))
    actual = [minor for _, minor in markers]
    if actual != expected:
        logger.warning(
            "Chapter %d sub-chapter markers are not monotonic (%s); leaving chapter un-subdivided",
            chapter_number,
            actual,
        )
        return [(None, chapter_text)]

    # Split at each marker. Any content before marker N.1 becomes its own
    # sub-chapter N.0 so its Narrator can be detected independently — publisher
    # chapters commonly open with several paragraphs of framing narration
    # (or a whole third-person interlude) before switching to N.1.
    parts: list[tuple[int | None, str]] = []
    first_marker_line = markers[0][0]
    lead_in = "".join(lines[:first_marker_line])
    if lead_in.strip():
        parts.append((0, lead_in.strip() + "\n"))
    for k, (line_idx, minor) in enumerate(markers):
        next_line = markers[k + 1][0] if k + 1 < len(markers) else len(lines)
        # Skip the marker line itself; body starts after it.
        body = "".join(lines[line_idx + 1 : next_line])
        parts.append((minor, body.strip() + "\n"))
    return parts


# ---------------------------------------------------------------------------
# ID helpers — canonical chapter identifier used in filenames and CLI args
# ---------------------------------------------------------------------------


def chapter_id(entry: dict) -> str:
    """Return the canonical chapter identifier for a manifest entry.

    Format: zero-padded main number, optionally suffixed with `_M` for
    sub-chapters. Examples: `"07"`, `"07_1"`, `"04b"` (publisher letter suffix
    preserved in `number` if it was ever set as a non-int).
    """
    num = entry["number"]
    sub = entry.get("subchapter")
    base = f"{num:02d}" if isinstance(num, int) else str(num)
    return f"{base}_{sub}" if sub is not None else base


def normalize_chapter_arg(arg: str) -> str:
    """Normalize a user-supplied chapter argument to canonical id form.

    `"7"` → `"07"`, `"7_1"` → `"07_1"`, `"4b"` → `"04b"`. Non-numeric leading
    tokens pass through unchanged.
    """
    match = re.match(r"^(\d+)(.*)", arg)
    if not match:
        return arg
    return match.group(1).zfill(2) + match.group(2)


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
        number (int), title (str), file (str), narrator_status, narrator.
    """
    # Wipe existing chapter_*.txt so a previous un-subdivided run doesn't leave
    # stale chapter_07.txt sitting next to the new chapter_07_1.txt. Manifest
    # is the source of truth; anything not written this run is obsolete.
    if output_dir.exists():
        for old in output_dir.glob("chapter_*.txt"):
            old.unlink()

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
                "narrator_status": "unset",
                "narrator": None,
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
                "narrator_status": "unset",
                "narrator": None,
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
        title = _extract_title(header_part)
        _write_chapter_entries(chapter_text, chapter_num, title, output_dir, manifest)

    return manifest


def _write_chapter_entries(
    chapter_text: str,
    chapter_num: int,
    title: str,
    output_dir: Path,
    manifest: list[dict],
    narrator_status: str = "unset",
    narrator: str | None = None,
) -> None:
    """Write chapter file(s) and append manifest entries, subdividing by `N.M`.

    If `_subdivide_by_subchapter` detects valid sub-chapter markers, writes one
    `chapter_{NN}_{M}.txt` per sub and appends a row with `subchapter=M`.
    Otherwise writes a single `chapter_{NN}.txt` with no subchapter field.
    """
    subs = _subdivide_by_subchapter(chapter_text, chapter_num)

    if len(subs) == 1 and subs[0][0] is None:
        filename = f"chapter_{chapter_num:02d}.txt"
        (output_dir / filename).write_text(chapter_text.strip() + "\n", encoding="utf-8")
        manifest.append(
            {
                "number": chapter_num,
                "title": title,
                "file": filename,
                "narrator_status": narrator_status,
                "narrator": narrator,
            }
        )
        return

    for minor, body in subs:
        filename = f"chapter_{chapter_num:02d}_{minor}.txt"
        (output_dir / filename).write_text(body, encoding="utf-8")
        manifest.append(
            {
                "number": chapter_num,
                "subchapter": minor,
                "title": f"{title} — Part {minor}",
                "file": filename,
                "narrator_status": "unset",
                "narrator": None,
            }
        )


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
        text = chapter.get("text", "")
        title = chapter.get("title", f"Chapter {chapter_num}")
        _write_chapter_entries(
            text,
            chapter_num,
            title,
            output_dir,
            manifest,
            narrator_status=chapter.get("narrator_status", "unset"),
            narrator=chapter.get("narrator"),
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
