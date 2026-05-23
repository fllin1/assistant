"""Configuration constants for the LN voice-over pipeline.

Central place for regex patterns, default settings, and directory conventions.
All pattern lists are meant to be extended by the user for specific books.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

DATA_DIR = Path.home() / ".assistant" / "ln_voice_over"
"""Root directory for all ln_voice_over data."""

PROJECTS_DIR = DATA_DIR / "projects"
"""Root directory for all book project data."""


def series_dir(series_slug: str) -> Path:
    """Return the root directory for a given series."""
    return PROJECTS_DIR / series_slug


def volume_dir(series_slug: str, volume_slug: str) -> Path:
    """Return the root directory for a given volume within a series."""
    return PROJECTS_DIR / series_slug / volume_slug


def project_dir(slug: str) -> Path:
    """Legacy helper returning a flat project directory.

    Kept for any remaining legacy callers. New code should use
    `series_dir()` or `volume_dir()`.
    """
    return PROJECTS_DIR / slug


SERIES_SUBDIRS = [
    "config",
]
"""Subdirectories created at the series level.

Config (characters.json, voices.json) lives here and is shared across all
volumes in the series. This is the key data-model decision behind the
nested layout: one cast, one voice map, many volumes.
"""


VOLUME_SUBDIRS = [
    "source",
    "chapters",
    "parsed",
    "extracted",
    "reviewed",
    "illustrations/images",
]
"""Subdirectories created inside each volume folder.

`source/` holds all pipeline inputs regardless of origin — a manually-prepared
.txt volume, a downloaded PDF + extracted page images, or a pre-structured
book.json from the /setup-book skill. The split stage auto-detects the format.
No `config/` here: configs are series-level only.
"""


# Alias kept for any transitional callers that still expect a flat list.
PROJECT_SUBDIRS = SERIES_SUBDIRS + VOLUME_SUBDIRS


# ---------------------------------------------------------------------------
# Stage 1: SPLIT — Chapter boundary detection
# ---------------------------------------------------------------------------

CHAPTER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"^Prologue\b", re.IGNORECASE),
    re.compile(r"^Epilogue\b", re.IGNORECASE),
    re.compile(r"^Interlude\b", re.IGNORECASE),
    re.compile(r"^Short\s+Stor(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"^Afterword\b", re.IGNORECASE),
    re.compile(r"^Bonus\b", re.IGNORECASE),
]
"""Regex patterns that mark the start of a new chapter.
Each pattern is tested against the start of a line."""

SUBCHAPTER_PATTERN: re.Pattern[str] = re.compile(r"^\s*(\d+)\.(\d+)\s*$")
"""Bare `N.M` on its own line — a sub-chapter boundary inside a main chapter.

The published books mark narrator-shifting sub-chapters this way: a bare `7.1` line,
blank line, then body text (no inline title). Treated as a boundary only when
the chapter has ≥ 2 such markers with matching major and strictly-increasing
minor starting from 1. See split._subdivide_by_subchapter."""

# ---------------------------------------------------------------------------
# Stage 2: PARSE — cleanup + segment classification
# ---------------------------------------------------------------------------

WATERMARK_PATTERNS: list[str] = [
    "Goldenagato",
    "mp4directs.com",
    "goldenagato",
]
"""Substrings that identify watermark-only lines (lines where the entire
content is a watermark). Add book-specific watermarks as needed."""

INLINE_WATERMARK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\s*Page\s+\d+\s+Goldenagato\s*\|\s*mp4directs\.com", re.IGNORECASE),
    re.compile(r"\s*Goldenagato\s*\|\s*mp4directs\.com", re.IGNORECASE),
]
"""Regex patterns for watermark suffixes embedded at the end of content lines.
These are stripped from the line rather than removing the line entirely."""

PAGE_NUMBER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*Page\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),
]
"""Patterns matching standalone page number lines."""

SCENE_BREAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*[*]{3,}\s*$"),
    re.compile(r"^\s*[-]{3,}\s*$"),
    re.compile(r"^\s*\*\s+\*\s+\*\s*$"),
    re.compile(r"^\s*[◇◆]+\s*$"),
]
"""Patterns identifying scene break lines. These are preserved during
cleaning and become SCENE_BREAK segments during parsing."""

MAX_CONSECUTIVE_BLANK_LINES = 2
"""Collapse runs of blank lines longer than this."""

MAX_SEGMENT_CHARS = 500
"""Long narration blocks exceeding this are split at sentence boundaries."""
