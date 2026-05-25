"""Dialogue stage contracts."""

from __future__ import annotations

from typing import Literal

from ...common.artifacts import ContractModel, PersistedArtifact
from ...common.enums import ArtifactKind, PerspectiveStatus, ReviewStatus
from ...common.ids import ChapterId, SegmentId


class Perspective(ContractModel):
    """Chapter narrator perspective decision."""

    status: PerspectiveStatus
    narrator: str | None


class DialogueRow(ContractModel):
    """Accepted or proposed spoken dialogue row."""

    segment_id: SegmentId
    speaker: str


class RejectedCandidate(ContractModel):
    """Quote-like segment rejected as dialogue."""

    segment_id: SegmentId
    reason: str


class DialogueChapter(PersistedArtifact):
    """Dialogue attribution artifact for one chapter."""

    artifact_kind: Literal[ArtifactKind.DIALOGUE_CHAPTER] = ArtifactKind.DIALOGUE_CHAPTER
    chapter_id: ChapterId
    status: ReviewStatus
    review_required: bool
    perspective: Perspective
    dialogues: tuple[DialogueRow, ...]
    rejected_candidates: tuple[RejectedCandidate, ...] = ()
    review_notes: tuple[str, ...] = ()
