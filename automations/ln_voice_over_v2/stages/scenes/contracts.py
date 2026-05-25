"""Scenes stage contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ...common.artifacts import ContractModel, PersistedArtifact
from ...common.enums import ArtifactKind, BeatType, ReviewStatus
from ...common.ids import AssetId, BeatId, ChapterId, SceneId, SegmentId


class Setting(ContractModel):
    """Scene setting metadata."""

    location: str
    time_of_day: str
    mood: str


class BackgroundChoice(ContractModel):
    """Background asset or generation prompt."""

    asset_id: AssetId | None = None
    prompt: str | None = None


class VisibleCharacter(ContractModel):
    """Character image choice inside a scene."""

    name: str
    image_id: AssetId
    position: str
    expression: str | None = None


class SceneBeat(ContractModel):
    """Renderable scene beat."""

    beat_id: BeatId
    beat_type: BeatType
    segment_id: SegmentId | None = None
    segment_ids: tuple[SegmentId, ...] = ()
    speaker: str | None = None
    spoken_text: str | None = None
    bubble_text: str | None = None
    visual_action: str | None = None
    silence_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_beat_shape(self) -> SceneBeat:
        """Enforce local beat shape constraints."""
        if self.beat_type == BeatType.DIALOGUE and self.segment_id is None:
            raise ValueError("dialogue beats require segment_id")
        if self.beat_type == BeatType.SILENCE and self.silence_ms is None:
            raise ValueError("silence beats require silence_ms")
        if self.beat_type not in {BeatType.DIALOGUE, BeatType.SILENCE} and not self.segment_ids:
            raise ValueError("non-dialogue source beats require segment_ids")
        return self


class Scene(ContractModel):
    """One visual/audio scene."""

    scene_id: SceneId
    segment_ids: tuple[SegmentId, ...]
    summary: str
    setting: Setting
    background: BackgroundChoice
    visible_characters: tuple[VisibleCharacter, ...]
    beats: tuple[SceneBeat, ...]


class SceneDocument(PersistedArtifact):
    """Draft or final scenes artifact."""

    artifact_kind: Literal[ArtifactKind.SCENES_DRAFT, ArtifactKind.SCENES_FINAL]
    chapter_id: ChapterId
    status: ReviewStatus
    review_required: bool
    scenes: tuple[Scene, ...]
