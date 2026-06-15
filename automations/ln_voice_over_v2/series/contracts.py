"""Series-level profile contracts for LNVO v2."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..common.artifacts import ContractModel
from ..common.ids import AssetId, ProfileId


class StoryProfile(ContractModel):
    """Story-specific rules shared by all volumes in a series."""

    schema_version: Literal[1] = 1
    profile_id: ProfileId
    display_name: str
    rules: dict[str, Any] = Field(default_factory=dict)


class Character(ContractModel):
    """Canonical character entry."""

    name: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    gender: str = "unknown"
    role: str = "minor"


class CharacterRegistry(ContractModel):
    """Series-level character source of truth."""

    schema_version: Literal[1] = 1
    characters: tuple[Character, ...] = ()

    def has_character(self, name: str) -> bool:
        """Return whether a canonical character name exists."""
        return any(character.name == name for character in self.characters)

    def resolve(self, name: str) -> str | None:
        """Resolve an exact character name or alias to its canonical name.

        Args:
            name: Raw character name or alias to resolve.

        Returns:
            The canonical character name when `name` exactly matches a
            character name or alias after trimming; otherwise `None`.
        """
        candidate = name.strip()
        for character in self.characters:
            if character.name == candidate:
                return character.name
            if candidate in character.aliases:
                return character.name
        return None


class VoiceMappingEntry(ContractModel):
    """Accepted TTS voice configuration for one voice key."""

    engine: str
    voice_id: str
    speed: float = 1.0
    params: dict[str, Any] = Field(default_factory=dict)
    playback_speed: float = 1.0


class VoiceMapping(ContractModel):
    """Series-level accepted voice mapping."""

    schema_version: Literal[1] = 1
    entries: dict[str, VoiceMappingEntry] = Field(default_factory=dict)


class NarrationProfile(ContractModel):
    """Series-level narration adaptation settings."""

    schema_version: Literal[1] = 1
    profile_id: ProfileId
    settings: dict[str, Any] = Field(default_factory=dict)


class VisualProfile(ContractModel):
    """Series-level visual assets and settings."""

    schema_version: Literal[1] = 1
    profile_id: ProfileId
    backgrounds: dict[AssetId, dict[str, Any]] = Field(default_factory=dict)
    character_images: dict[AssetId, dict[str, Any]] = Field(default_factory=dict)


class RenderProfile(ContractModel):
    """Series-level final render settings."""

    schema_version: Literal[1] = 1
    profile_id: ProfileId
    width: int
    height: int
    fps: int
    audio_format: str
    video_format: str
