"""Validation for dialogue-stage artifacts."""

from ...common.enums import ReviewStatus
from ...common.errors import ContractValidationError, ValidationProblem
from ...common.ids import SegmentId
from .contracts import DialogueChapter


def validate_dialogue_artifact(
    dialogue: DialogueChapter, candidate_ids: tuple[SegmentId, ...]
) -> None:
    """Validate dialogue-stage coverage and review status consistency."""
    problems: list[ValidationProblem] = []
    dialogue_ids = {row.segment_id for row in dialogue.dialogues}
    rejected_ids = {candidate.segment_id for candidate in dialogue.rejected_candidates}
    candidate_id_set = set(candidate_ids)

    for segment_id in sorted(candidate_id_set - (dialogue_ids | rejected_ids)):
        problems.append(
            ValidationProblem(
                code="uncovered_candidate",
                message=f"Candidate segment is not covered: {segment_id}",
                path=f"candidates.{segment_id}",
            )
        )

    for segment_id in sorted(dialogue_ids & rejected_ids):
        problems.append(
            ValidationProblem(
                code="candidate_in_both",
                message=f"Candidate segment appears in dialogue and rejected lists: {segment_id}",
                path=f"dialogue.{segment_id}",
            )
        )

    needs_review = dialogue.status == ReviewStatus.NEEDS_REVIEW
    if needs_review != dialogue.review_required:
        problems.append(
            ValidationProblem(
                code="status_mismatch",
                message="Dialogue status must match review_required",
                path="status",
            )
        )

    if problems:
        raise ContractValidationError(problems)
