"""Data models for the LN voice-over pipeline.

All models are pydantic BaseModel with frozen config — immutable after
creation. Use .model_copy(update={...}) to create modified copies.

Models with file I/O needs (Chapter, CharacterRegistry) have
.save(path) / .load(path) classmethods for JSON round-trip with atomic writes.
"""

from __future__ import annotations

import tempfile
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


def _atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.rename(path)


class SegmentType(Enum):
    """Classification of a text segment."""

    NARRATION = "narration"
    DIALOGUE = "dialogue"
    SCENE_BREAK = "scene_break"
    CHAPTER_HEADER = "chapter_header"


class NarratorStatus(Enum):
    """Whether narrator detection has run for a chapter."""

    UNSET = "unset"
    DETECTED = "detected"


class Segment(BaseModel):
    """A single segment of chapter text.

    Created by the PARSE stage with speaker as None.
    The RESOLVE stage produces new Segment instances (via model_copy())
    with speaker populated.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    index: int
    segment_type: SegmentType
    text: str
    speaker: str | None = None


class Chapter(BaseModel):
    """A chapter with all its segments.

    The narrator fields drive voice selection for Narrator-labeled segments.
    When narrator_status is "unset", detection has not run. When it is
    "detected", narrator is authoritative: a character name means first-person
    narration, while None means the omniscient narrator.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    chapter_number: int
    subchapter: int | None = None
    title: str
    source_file: str
    narrator_status: NarratorStatus
    narrator: str | None
    segments: tuple[Segment, ...]
    reviewed: bool = False

    @property
    def chapter_id(self) -> str:
        """Canonical filename-safe identifier (e.g. `"07"` or `"07_1"`)."""
        base = f"{self.chapter_number:02d}"
        return f"{base}_{self.subchapter}" if self.subchapter is not None else base

    def save(self, path: Path) -> None:
        """Atomic write to JSON file."""
        _atomic_write(path, self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> Chapter:
        """Read a Chapter from a JSON file."""
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


class Character(BaseModel):
    """A character in the character registry.

    Attributes:
        name: Canonical name used for attribution and voice mapping.
        aliases: Alternative names/spellings the LLM might use.
        description: Brief description for LLM context during attribution.
        gender: Used for fallback voice selection ("male", "female", "unknown").
        role: Affects voice assignment priority ("main", "supporting", "minor").
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    gender: str = "unknown"
    role: str = "minor"


class CharacterRegistry(BaseModel):
    """All known characters for a book or series.

    The registry is the source of truth for character names during
    attribution and voice resolution. The find() method handles
    case-insensitive lookup by name or alias.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    characters: tuple[Character, ...] = ()
    narrator_name: str = "Narrator"

    def find(self, name: str) -> Character | None:
        """Look up a character by name or alias (case-insensitive)."""
        lower = name.lower()
        for character in self.characters:
            if character.name.lower() == lower:
                return character
            if lower in (alias.lower() for alias in character.aliases):
                return character
        return None

    def fuzzy_find(self, name: str, cutoff: float = 0.6) -> Character | None:
        """Look up a character with fuzzy matching as fallback.

        Tries exact match first, then strips honorific suffixes,
        then falls back to difflib fuzzy matching against all known names.
        """
        honorific_suffixes = ["-sensei", "-san", "-kun", "-chan", "-sama", "-senpai"]

        # Exact match
        exact = self.find(name)
        if exact:
            return exact

        # Strip honorific suffix and retry
        stripped = name
        for suffix in honorific_suffixes:
            if name.lower().endswith(suffix):
                stripped = name[: -len(suffix)]
                break
        if stripped != name:
            exact = self.find(stripped)
            if exact:
                return exact

        # Component match: "Kiriyama" matches "Kiriyama Ikuto",
        # "Ike Kakeru" matches "Ike Kanji" via shared surname "Ike"
        input_parts = stripped.lower().split()
        for part in input_parts:
            if len(part) < 2:
                continue
            for character in self.characters:
                if part in character.name.lower().split():
                    return character
                for alias in character.aliases:
                    if part in alias.lower().split():
                        return character

        # Fuzzy match against all canonical names and aliases
        all_names: dict[str, Character] = {}
        for character in self.characters:
            all_names[character.name] = character
            for alias in character.aliases:
                all_names[alias] = character

        from difflib import get_close_matches

        matches = get_close_matches(name, all_names.keys(), n=1, cutoff=cutoff)
        if matches:
            return all_names[matches[0]]
        return None

    def save(self, path: Path) -> None:
        """Atomic write to JSON file."""
        _atomic_write(path, self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> CharacterRegistry:
        """Read a CharacterRegistry from a JSON file."""
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
