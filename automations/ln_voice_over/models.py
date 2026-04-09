"""Data models for the LN voice-over pipeline.

All models are frozen dataclasses — immutable after creation. Collection
fields use tuples (not lists) so immutability is genuine. Use
dataclasses.replace() to create modified copies.

The Segment model accumulates optional fields across stages:
- After PARSE: index, segment_type, text, line_start, line_end
- After ATTRIBUTE: + speaker, confidence
"""

from __future__ import annotations

from dataclasses import dataclass
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

    Created by the PARSE stage with speaker/confidence as None.
    The ATTRIBUTE stage produces new Segment instances (via replace())
    with speaker and confidence populated.
    """

    index: int
    segment_type: SegmentType
    text: str
    line_start: int
    line_end: int
    speaker: str | None = None
    confidence: float | None = None


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

    characters: tuple[Character, ...]
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

    mappings: tuple[VoiceMapping, ...]
    default_male: VoiceMapping
    default_female: VoiceMapping
    default_narrator: VoiceMapping

    def get_voice(
        self, speaker: str, gender: str = "unknown"
    ) -> VoiceMapping:
        """Resolve a speaker to a voice mapping with fallback logic."""
        for mapping in self.mappings:
            if mapping.speaker == speaker:
                return mapping
        if gender == "male":
            return self.default_male
        if gender == "female":
            return self.default_female
        return self.default_narrator
