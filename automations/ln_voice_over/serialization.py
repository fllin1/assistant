"""JSON serialization for pipeline data models.

Handles the round-trip between frozen dataclasses and JSON files.
Uses dataclasses.asdict() for serialization and manual construction
for deserialization (frozen dataclasses need constructor calls, not
field mutation).

Each model pair: X_to_dict / X_from_dict for in-memory conversion,
save_X / load_X for file I/O.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Chapter, CharacterRegistry, Segment, VoiceConfig


def segment_to_dict(segment: Segment) -> dict:
    """Convert a Segment to a JSON-serializable dict.

    The segment_type enum is stored as its string value.
    None fields (speaker, confidence) are included for schema consistency.
    """
    ...


def segment_from_dict(data: dict) -> Segment:
    """Reconstruct a Segment from a dict.

    Converts the segment_type string back to SegmentType enum.
    """
    ...


def chapter_to_dict(chapter: Chapter) -> dict:
    """Convert a Chapter (with all segments) to a JSON-serializable dict."""
    ...


def chapter_from_dict(data: dict) -> Chapter:
    """Reconstruct a Chapter from a dict.

    Segments are deserialized as a tuple of Segment instances.
    """
    ...


def save_chapter(chapter: Chapter, path: Path) -> None:
    """Write a Chapter to a JSON file (indented, human-readable).

    Writes to a temporary file first, then renames for atomicity.
    """
    ...


def load_chapter(path: Path) -> Chapter:
    """Read a Chapter from a JSON file."""
    ...


def registry_to_dict(registry: CharacterRegistry) -> dict:
    """Convert a CharacterRegistry to a JSON-serializable dict."""
    ...


def registry_from_dict(data: dict) -> CharacterRegistry:
    """Reconstruct a CharacterRegistry from a dict."""
    ...


def save_registry(registry: CharacterRegistry, path: Path) -> None:
    """Write a CharacterRegistry to a JSON file."""
    ...


def load_registry(path: Path) -> CharacterRegistry:
    """Read a CharacterRegistry from a JSON file."""
    ...


def voice_config_to_dict(config: VoiceConfig) -> dict:
    """Convert a VoiceConfig to a JSON-serializable dict."""
    ...


def voice_config_from_dict(data: dict) -> VoiceConfig:
    """Reconstruct a VoiceConfig from a dict."""
    ...


def save_voice_config(config: VoiceConfig, path: Path) -> None:
    """Write a VoiceConfig to a JSON file."""
    ...


def load_voice_config(path: Path) -> VoiceConfig:
    """Read a VoiceConfig from a JSON file."""
    ...
