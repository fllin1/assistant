"""Transform stage contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ...common.artifacts import ContractModel, PersistedArtifact
from ...common.enums import ArtifactKind
from ...common.ids import ArtifactPath, ChapterId, SegmentId, TextUnitId


class ChapterIndexEntry(ContractModel):
    """Volume index entry for one chapter artifact."""

    chapter_id: ChapterId
    order: int = Field(ge=0)
    segments_file: ArtifactPath
    display_name: str = Field(min_length=1)


class VolumeIndex(PersistedArtifact):
    """Transform volume index artifact."""

    artifact_kind: Literal[ArtifactKind.VOLUME_INDEX] = ArtifactKind.VOLUME_INDEX
    chapter_id: None = None
    chapters: tuple[ChapterIndexEntry, ...]


class Segment(ContractModel):
    """Stable chapter text segment."""

    segment_id: SegmentId
    order: int = Field(ge=0)
    text: str
    source_unit_ids: tuple[TextUnitId, ...] = ()
    parser_hints: dict[str, Any] = Field(default_factory=dict)


class SegmentFile(PersistedArtifact):
    """Chapter segment artifact."""

    artifact_kind: Literal[ArtifactKind.SEGMENT_FILE] = ArtifactKind.SEGMENT_FILE
    chapter_id: ChapterId
    segments: tuple[Segment, ...]
