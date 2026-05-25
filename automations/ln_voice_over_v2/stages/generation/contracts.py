"""Generation stage contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ...common.artifacts import ContractModel, PersistedArtifact
from ...common.enums import ArtifactKind, BeatType, StageStatus
from ...common.ids import ArtifactPath, AssetId, BeatId, ChapterId, ProfileId


class GenerationOutputs(ContractModel):
    """Generated media and manifest paths."""

    audio: ArtifactPath
    audio_manifest: ArtifactPath
    timeline: ArtifactPath
    video: ArtifactPath


class GenerationManifest(PersistedArtifact):
    """Generation package manifest."""

    artifact_kind: Literal[ArtifactKind.GENERATION_MANIFEST] = ArtifactKind.GENERATION_MANIFEST
    chapter_id: ChapterId
    status: StageStatus
    scene_source: ArtifactPath
    outputs: GenerationOutputs
    render_profile: ProfileId
    voice_mapping: ArtifactPath


class AudioBeat(ContractModel):
    """Audio timing and stem record for one beat."""

    beat_id: BeatId
    beat_type: BeatType
    speaker: str | None = None
    voice_key: str | None = None
    engine: str | None = None
    voice_id: str | None = None
    cache_key: str | None = None
    stem: ArtifactPath
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    silence_ms: int | None = Field(default=None, ge=0)


class AudioManifest(PersistedArtifact):
    """Audio render manifest."""

    artifact_kind: Literal[ArtifactKind.AUDIO_MANIFEST] = ArtifactKind.AUDIO_MANIFEST
    chapter_id: ChapterId
    beats: tuple[AudioBeat, ...]


class VisualBeat(ContractModel):
    """Timed visual state for one beat."""

    beat_id: BeatId
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    background: AssetId
    visible_characters: tuple[AssetId, ...]
    bubble_text: str | None = None
    visual_action: str | None = None


class VisualTimeline(PersistedArtifact):
    """Visual timeline manifest."""

    artifact_kind: Literal[ArtifactKind.VISUAL_TIMELINE] = ArtifactKind.VISUAL_TIMELINE
    chapter_id: ChapterId
    beats: tuple[VisualBeat, ...]
