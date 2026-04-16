"""Data models for the LN voice-over pipeline.

All models are frozen dataclasses — immutable after creation. Collection
fields use tuples (not lists) so immutability is genuine. Use
dataclasses.replace() to create modified copies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SegmentType(Enum):
    """Classification of a text segment."""

    NARRATION = "narration"
    DIALOGUE = "dialogue"
    INNER_THOUGHT = "inner_thought"
    SCENE_BREAK = "scene_break"
    CHAPTER_HEADER = "chapter_header"


@dataclass(frozen=True)
class Segment:
    """A single segment of chapter text.

    Created by the PARSE stage with speaker as None.
    The RESOLVE stage produces new Segment instances (via replace())
    with speaker populated.
    """

    index: int
    segment_type: SegmentType
    text: str
    speaker: str | None = None


@dataclass(frozen=True)
class Chapter:
    """A chapter with all its segments.

    The pov_character field drives narrator voice selection: when set,
    all narration segments in this chapter use that character's voice
    instead of the default narrator voice.
    """

    chapter_number: int
    title: str
    source_file: str
    pov_character: str | None
    segments: tuple[Segment, ...]
    reviewed: bool = False


@dataclass(frozen=True)
class Character:
    """A character in the character registry.

    Attributes:
        name: Canonical name used for attribution and voice mapping.
        aliases: Alternative names/spellings the LLM might use.
        description: Brief description for LLM context during attribution.
        gender: Used for fallback voice selection ("male", "female", "unknown").
        role: Affects voice assignment priority ("main", "supporting", "minor").
    """

    name: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    gender: str = "unknown"
    role: str = "minor"


@dataclass(frozen=True)
class CharacterRegistry:
    """All known characters for a book or series.

    The registry is the source of truth for character names during
    attribution and voice resolution. The find() method handles
    case-insensitive lookup by name or alias.
    """

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


@dataclass(frozen=True)
class VoiceMapping:
    """Maps a speaker to a TTS voice.

    Attributes:
        speaker: Character.name or "Narrator".
        provider: TTS provider key ("edge", "elevenlabs", "openai").
        voice_id: Provider-specific voice identifier.
        settings: Optional provider-specific params (speed, pitch, etc.).
    """

    speaker: str
    provider: str
    voice_id: str
    settings: dict | None = None


@dataclass(frozen=True)
class VoiceConfig:
    """Complete voice configuration for a project.

    Resolution order in get_voice():
    1. Exact speaker match in mappings
    2. Gender-based default (default_male / default_female)
    3. default_narrator as final fallback
    """

    mappings: tuple[VoiceMapping, ...] = ()
    default_male: VoiceMapping = field(
        default_factory=lambda: VoiceMapping(
            speaker="__default_male__", provider="edge", voice_id="en-US-GuyNeural"
        )
    )
    default_female: VoiceMapping = field(
        default_factory=lambda: VoiceMapping(
            speaker="__default_female__", provider="edge", voice_id="en-US-JennyNeural"
        )
    )
    default_narrator: VoiceMapping = field(
        default_factory=lambda: VoiceMapping(
            speaker="Narrator", provider="edge", voice_id="en-US-AriaNeural"
        )
    )

    def get_voice(self, speaker: str, gender: str = "unknown") -> VoiceMapping:
        """Resolve a speaker to a voice mapping with fallback logic."""
        for mapping in self.mappings:
            if mapping.speaker == speaker:
                return mapping
        if gender == "male":
            return self.default_male
        if gender == "female":
            return self.default_female
        return self.default_narrator
