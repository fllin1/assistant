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
import tempfile
from dataclasses import asdict
from pathlib import Path

from .models import (
    Chapter,
    Character,
    CharacterRegistry,
    Segment,
    SegmentType,
    VoiceConfig,
    VoiceMapping,
)

# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------


def segment_to_dict(segment: Segment) -> dict:
    """Convert a Segment to a JSON-serializable dict.

    The segment_type enum is stored as its string value.
    None fields (speaker, confidence) are included for schema consistency.
    """
    d = asdict(segment)
    d["segment_type"] = segment.segment_type.value
    return d


def segment_from_dict(data: dict) -> Segment:
    """Reconstruct a Segment from a dict.

    Converts the segment_type string back to SegmentType enum.
    """
    return Segment(
        index=data["index"],
        segment_type=SegmentType(data["segment_type"]),
        text=data["text"],
        line_start=data["line_start"],
        line_end=data["line_end"],
        speaker=data.get("speaker"),
        confidence=data.get("confidence"),
        attribution_method=data.get("attribution_method"),
    )


# ---------------------------------------------------------------------------
# Chapter
# ---------------------------------------------------------------------------


def chapter_to_dict(chapter: Chapter) -> dict:
    """Convert a Chapter (with all segments) to a JSON-serializable dict."""
    return {
        "chapter_number": chapter.chapter_number,
        "title": chapter.title,
        "source_file": chapter.source_file,
        "pov_character": chapter.pov_character,
        "reviewed": chapter.reviewed,
        "segments": [segment_to_dict(s) for s in chapter.segments],
    }


def chapter_from_dict(data: dict) -> Chapter:
    """Reconstruct a Chapter from a dict.

    Segments are deserialized as a tuple of Segment instances.
    """
    return Chapter(
        chapter_number=data["chapter_number"],
        title=data["title"],
        source_file=data["source_file"],
        pov_character=data.get("pov_character"),
        segments=tuple(segment_from_dict(s) for s in data["segments"]),
        reviewed=data.get("reviewed", False),
    )


def save_chapter(chapter: Chapter, path: Path) -> None:
    """Write a Chapter to a JSON file (indented, human-readable).

    Writes to a temporary file first, then renames for atomicity.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = chapter_to_dict(chapter)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.rename(path)


def load_chapter(path: Path) -> Chapter:
    """Read a Chapter from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return chapter_from_dict(data)


# ---------------------------------------------------------------------------
# CharacterRegistry
# ---------------------------------------------------------------------------


def _character_to_dict(character: Character) -> dict:
    d = asdict(character)
    # asdict converts tuples to lists — fine for JSON
    return d


def _character_from_dict(data: dict) -> Character:
    return Character(
        name=data["name"],
        aliases=tuple(data.get("aliases", ())),
        description=data.get("description", ""),
        gender=data.get("gender", "unknown"),
        role=data.get("role", "minor"),
    )


def registry_to_dict(registry: CharacterRegistry) -> dict:
    """Convert a CharacterRegistry to a JSON-serializable dict."""
    return {
        "narrator_name": registry.narrator_name,
        "characters": [_character_to_dict(c) for c in registry.characters],
    }


def registry_from_dict(data: dict) -> CharacterRegistry:
    """Reconstruct a CharacterRegistry from a dict."""
    return CharacterRegistry(
        characters=tuple(_character_from_dict(c) for c in data["characters"]),
        narrator_name=data.get("narrator_name", "Narrator"),
    )


def save_registry(registry: CharacterRegistry, path: Path) -> None:
    """Write a CharacterRegistry to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = registry_to_dict(registry)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.rename(path)


def load_registry(path: Path) -> CharacterRegistry:
    """Read a CharacterRegistry from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return registry_from_dict(data)


# ---------------------------------------------------------------------------
# VoiceConfig
# ---------------------------------------------------------------------------


def _voice_mapping_to_dict(mapping: VoiceMapping) -> dict:
    return asdict(mapping)


def _voice_mapping_from_dict(data: dict) -> VoiceMapping:
    return VoiceMapping(
        speaker=data["speaker"],
        provider=data["provider"],
        voice_id=data["voice_id"],
        settings=data.get("settings"),
    )


def voice_config_to_dict(config: VoiceConfig) -> dict:
    """Convert a VoiceConfig to a JSON-serializable dict."""
    return {
        "mappings": [_voice_mapping_to_dict(m) for m in config.mappings],
        "default_male": _voice_mapping_to_dict(config.default_male),
        "default_female": _voice_mapping_to_dict(config.default_female),
        "default_narrator": _voice_mapping_to_dict(config.default_narrator),
    }


def voice_config_from_dict(data: dict) -> VoiceConfig:
    """Reconstruct a VoiceConfig from a dict."""
    return VoiceConfig(
        mappings=tuple(_voice_mapping_from_dict(m) for m in data["mappings"]),
        default_male=_voice_mapping_from_dict(data["default_male"]),
        default_female=_voice_mapping_from_dict(data["default_female"]),
        default_narrator=_voice_mapping_from_dict(data["default_narrator"]),
    )


def save_voice_config(config: VoiceConfig, path: Path) -> None:
    """Write a VoiceConfig to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = voice_config_to_dict(config)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.rename(path)


def load_voice_config(path: Path) -> VoiceConfig:
    """Read a VoiceConfig from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return voice_config_from_dict(data)
