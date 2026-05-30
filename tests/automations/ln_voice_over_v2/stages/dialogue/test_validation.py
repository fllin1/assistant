"""Tests for dialogue artifact validation."""

import pytest
from automations.ln_voice_over_v2.common.enums import PerspectiveStatus, ReviewStatus
from automations.ln_voice_over_v2.common.errors import ContractValidationError
from automations.ln_voice_over_v2.stages.dialogue.contracts import (
    DialogueChapter,
    DialogueRow,
    Perspective,
    RejectedCandidate,
)
from automations.ln_voice_over_v2.stages.dialogue.validation import (
    validate_dialogue_artifact,
)


def _perspective() -> Perspective:
    return Perspective(
        status=PerspectiveStatus.DETECTED,
        narrator="Narrator",
    )


def _dialogue_chapter(
    *,
    dialogues: tuple[DialogueRow, ...] = (),
    rejected_candidates: tuple[RejectedCandidate, ...] = (),
    status: ReviewStatus = ReviewStatus.ACCEPTED,
    review_required: bool = False,
) -> DialogueChapter:
    return DialogueChapter(
        series="series-1",
        volume="volume-1",
        chapter_id="chapter_01",
        dialogues=dialogues,
        rejected_candidates=rejected_candidates,
        perspective=_perspective(),
        status=status,
        review_required=review_required,
        review_notes=(),
    )


def _dialogue_row(segment_id: str) -> DialogueRow:
    return DialogueRow(
        segment_id=segment_id,
        speaker="Ann",
    )


def _rejected_candidate(segment_id: str) -> RejectedCandidate:
    return RejectedCandidate(
        segment_id=segment_id,
        reason="quoted narration",
    )


def test_validate_dialogue_artifact_valid_passes():
    artifact = _dialogue_chapter(
        dialogues=(_dialogue_row("seg_000001"),),
        rejected_candidates=(_rejected_candidate("seg_000002"),),
    )

    validate_dialogue_artifact(artifact, ("seg_000001", "seg_000002"))


def test_validate_dialogue_artifact_uncovered_candidate():
    artifact = _dialogue_chapter(dialogues=(_dialogue_row("seg_000001"),))

    with pytest.raises(ContractValidationError) as exc_info:
        validate_dialogue_artifact(artifact, ("seg_000001", "seg_000002"))

    assert exc_info.value.problems[0].code == "uncovered_candidate"


def test_validate_dialogue_artifact_candidate_in_both():
    artifact = _dialogue_chapter(
        dialogues=(_dialogue_row("seg_000001"),),
        rejected_candidates=(_rejected_candidate("seg_000001"),),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_dialogue_artifact(artifact, ("seg_000001",))

    assert exc_info.value.problems[0].code == "candidate_in_both"


def test_validate_dialogue_artifact_status_mismatch():
    artifact = _dialogue_chapter(
        dialogues=(_dialogue_row("seg_000001"),),
        status=ReviewStatus.NEEDS_REVIEW,
        review_required=False,
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_dialogue_artifact(artifact, ("seg_000001",))

    assert exc_info.value.problems[0].code == "status_mismatch"
