"""Orchestration data contracts for LNVO v2."""

from __future__ import annotations

from ..common.artifacts import ContractModel
from ..common.enums import PipelineStage, StageStatus
from ..common.errors import ValidationProblem
from ..common.ids import ArtifactPath, ChapterId, SeriesId, VolumeId


class VolumeTarget(ContractModel):
    """A volume-level pipeline target."""

    series: SeriesId
    volume: VolumeId


class ChapterTarget(VolumeTarget):
    """A chapter-level pipeline target."""

    chapter_id: ChapterId


class StageResult(ContractModel):
    """Result record for one pipeline stage."""

    stage: PipelineStage
    status: StageStatus
    artifacts: tuple[ArtifactPath, ...] = ()
    problems: tuple[ValidationProblem, ...] = ()


class PipelineRun(ContractModel):
    """Volume-first orchestration record."""

    series: SeriesId
    volume: VolumeId
    stages: tuple[StageResult, ...] = ()
    status: StageStatus = StageStatus.PENDING
