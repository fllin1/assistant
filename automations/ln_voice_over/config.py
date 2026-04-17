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


def project_dir(slug: str) -> Path:
    """Return the root directory for a given book project."""
    return PROJECTS_DIR / slug


PROJECT_SUBDIRS = [
    "config",
    "config/extractions",
    "source",
    "chapters",
    "cleaned",
    "parsed",
    "extracted",
    "resolved",
    "reviewed",
    "illustrations/images",
    "audio/segments",
    "audio/chapters",
]
"""Subdirectories created inside each project folder.

`source/` holds all pipeline inputs regardless of origin — a manually-prepared
.txt volume, a downloaded PDF + extracted page images, or a pre-structured
book.json from the /setup-book skill. The split stage auto-detects the format.
"""


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

# ---------------------------------------------------------------------------
# Stage 2: CLEAN — Artifact removal
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

# ---------------------------------------------------------------------------
# Stage 3: PARSE — Segment classification
# ---------------------------------------------------------------------------

MAX_SEGMENT_CHARS = 500
"""Long narration blocks exceeding this are split at sentence boundaries."""

# ---------------------------------------------------------------------------
# Stage 4: ATTRIBUTE — LLM settings
# ---------------------------------------------------------------------------

DEFAULT_LLM_MODEL = "gemma4:26b"

# Model registry: short alias → (provider, model_id)
# Provider is "ollama" (local) or "openrouter" (cloud via OpenAI-compatible API).
# Use the alias as --model in CLI commands.
MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    "gemma4:26b": ("ollama", "gemma4:26b"),
    "gemma4:12b": ("ollama", "gemma4:12b"),
    "gemini-flash-lite": ("openrouter", "google/gemini-3.1-flash-lite-preview"),
    "gemini-flash": ("openrouter", "google/gemini-3-flash-preview"),
    "grok-fast": ("openrouter", "x-ai/grok-4.1-fast"),
}
"""Model alias → (provider, model_id). Provider is "ollama" or "openrouter"."""

# ---------------------------------------------------------------------------
# Stage 6: SYNTHESIZE — TTS and assembly
# ---------------------------------------------------------------------------

DEFAULT_TTS_PROVIDER = "edge"

SILENCE_DURATIONS_MS: dict[str, int] = {
    "dialogue_to_dialogue": 200,
    "narration_to_dialogue": 400,
    "dialogue_to_narration": 400,
    "scene_break": 800,
    "chapter_header": 1500,
    "default": 300,
}
"""Silence inserted between segments during assembly (milliseconds)."""
