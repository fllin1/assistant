"""Prepare stage contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ...common.artifacts import ContractModel, PersistedArtifact
from ...common.enums import ArtifactKind, MediaType
from ...common.ids import ArtifactPath, AssetId, ProfileId, TextUnitId


class PreparedTextUnit(ContractModel):
    """Ordered normalized text block."""

    text_unit_id: TextUnitId
    order: int = Field(ge=0)
    text: str
    source_path: ArtifactPath
    source_locator: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    needs_review: bool = False


class PreparedMedia(ContractModel):
    """Prepared media inventory entry."""

    media_id: AssetId
    order: int = Field(ge=0)
    media_type: MediaType
    path: ArtifactPath
    source_path: ArtifactPath


class PreparedVolume(PersistedArtifact):
    """Prepared volume artifact."""

    artifact_kind: Literal[ArtifactKind.PREPARED_VOLUME] = ArtifactKind.PREPARED_VOLUME
    chapter_id: None = None
    story_profile: ProfileId
    source_profile: ProfileId
    text_units: tuple[PreparedTextUnit, ...]
    media: tuple[PreparedMedia, ...] = ()
