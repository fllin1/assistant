"""Base models for public LNVO v2 contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .enums import ArtifactKind
from .ids import ChapterId, SeriesId, VolumeId


class ContractModel(BaseModel):
    """Base class for non-persisted public contract models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PersistedArtifact(ContractModel):
    """Flat base shape for persisted stage artifacts."""

    schema_version: Literal[1] = 1
    artifact_kind: ArtifactKind
    series: SeriesId
    volume: VolumeId
    chapter_id: ChapterId | None = None
