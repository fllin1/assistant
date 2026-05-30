"""Run dialogue attribution for a prepared chapter."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...common import paths
from ...common.enums import PerspectiveStatus, ReviewStatus
from ...common.errors import ContractValidationError, ValidationProblem
from ...common.ids import ChapterId, SeriesId, VolumeId
from ...common.json_io import load_json_contract, save_json_contract
from ...pipeline.validators import UNKNOWN_SPEAKER, validate_dialogue_against_segments
from ...series.contracts import CharacterRegistry
from ..transform.contracts import SegmentFile, VolumeIndex
from .agent import DialogueProposal, run_codex_dialogue
from .config import (
    load_character_registry,
    load_story_profile,
    resolve_story_profile_path,
)
from .context import ChapterPayload, build_chapter_payload
from .contracts import DialogueChapter, DialogueRow, Perspective, RejectedCandidate
from .names import canonical_narrator, canonical_speaker
from .prompts import build_prompt
from .validation import validate_dialogue_artifact

logger = logging.getLogger("ln_voice_over_v2.dialogue.runner")

AttributeFn = Callable[[ChapterPayload], DialogueProposal]


@dataclass(frozen=True)
class DialogueConfig:
    """Configuration for running dialogue attribution on one chapter."""

    series: SeriesId
    volume: VolumeId
    chapter_id: ChapterId
    data_root: Path = paths.DEFAULT_PROJECT_DATA_ROOT
    force: bool = False


@dataclass(frozen=True)
class DialogueResult:
    """Result of a dialogue attribution run."""

    dialogue_path: Path
    dialogue: DialogueChapter
    accepted_count: int
    rejected_count: int
    review_required: bool
    skipped: bool


def run_dialogue(
    config: DialogueConfig,
    *,
    attribute_fn: AttributeFn | None = None,
) -> DialogueResult:
    """Run dialogue attribution for one chapter and write the artifact."""

    dialogue_path = paths.dialogue_chapter_path(
        config.data_root,
        config.series,
        config.volume,
        config.chapter_id,
    )
    if dialogue_path.exists() and not config.force:
        logger.info("Dialogue artifact exists; skipping: %s", dialogue_path)
        dialogue = load_json_contract(dialogue_path, DialogueChapter)
        return DialogueResult(
            dialogue_path=dialogue_path,
            dialogue=dialogue,
            accepted_count=len(dialogue.dialogues),
            rejected_count=len(dialogue.rejected_candidates),
            review_required=dialogue.review_required,
            skipped=True,
        )

    volume_index = load_json_contract(
        paths.volume_index_path(config.data_root, config.series, config.volume),
        VolumeIndex,
    )
    chapter_ids = {chapter.chapter_id for chapter in volume_index.chapters}
    if config.chapter_id not in chapter_ids:
        raise ContractValidationError(
            [
                ValidationProblem(
                    code="unknown_chapter",
                    message=f"Chapter {config.chapter_id} is not in volume index",
                    path="chapter_id",
                )
            ]
        )

    segment_file = load_json_contract(
        paths.segment_file_path(
            config.data_root,
            config.series,
            config.volume,
            config.chapter_id,
        ),
        SegmentFile,
    )
    registry = load_character_registry(
        paths.characters_config_path(config.data_root, config.series)
    )
    story_profile = load_story_profile(resolve_story_profile_path(config.data_root, config.series))
    payload = build_chapter_payload(segment_file, story_profile)
    candidate_ids = payload.candidate_ids
    candidate_id_set = set(candidate_ids)

    if attribute_fn is None:

        def attribute_fn(payload: ChapterPayload) -> DialogueProposal:
            return run_codex_dialogue(build_prompt(payload, _roster(registry)))

    proposal = attribute_fn(payload)

    segment_order = {
        segment.segment_id: index for index, segment in enumerate(segment_file.segments)
    }
    all_segment_ids = set(segment_order)
    decision_by_id = {}
    stray_notes: list[str] = []
    rejected: list[RejectedCandidate] = []
    omitted_candidate = False

    for decision in proposal.decisions:
        if decision.segment_id in candidate_id_set:
            decision_by_id[decision.segment_id] = decision
        elif decision.segment_id in all_segment_ids:
            rejected.append(
                RejectedCandidate(
                    segment_id=decision.segment_id,
                    reason="model_stray_segment",
                )
            )
        else:
            stray_notes.append(f"stray segment {decision.segment_id} ignored")

    narrator = canonical_narrator(proposal.narrator_raw, registry)
    dialogues: list[DialogueRow] = []
    for segment_id in candidate_ids:
        decision = decision_by_id.get(segment_id)
        if decision is None:
            omitted_candidate = True
            rejected.append(RejectedCandidate(segment_id=segment_id, reason="model_omitted"))
        elif decision.is_dialogue:
            dialogues.append(
                DialogueRow(
                    segment_id=segment_id,
                    speaker=canonical_speaker(
                        decision.speaker_raw,
                        registry,
                        narrator=narrator,
                    ),
                )
            )
        else:
            rejected.append(
                RejectedCandidate(
                    segment_id=segment_id,
                    reason=decision.reason or "rejected",
                )
            )

    review_notes = tuple((*proposal.review_notes, *stray_notes))
    review_required = (
        any(row.speaker == UNKNOWN_SPEAKER for row in dialogues)
        or narrator is None
        or omitted_candidate
        or bool(review_notes)
    )
    status = ReviewStatus.NEEDS_REVIEW if review_required else ReviewStatus.ACCEPTED
    perspective = Perspective(
        status=(PerspectiveStatus.DETECTED if narrator is not None else PerspectiveStatus.UNSET),
        narrator=narrator,
    )

    dialogues.sort(key=lambda row: segment_order[row.segment_id])
    rejected.sort(key=lambda row: segment_order[row.segment_id])

    dialogue = DialogueChapter(
        series=config.series,
        volume=config.volume,
        chapter_id=config.chapter_id,
        status=status,
        review_required=review_required,
        perspective=perspective,
        dialogues=tuple(dialogues),
        rejected_candidates=tuple(rejected),
        review_notes=review_notes,
    )

    validate_dialogue_artifact(dialogue, candidate_ids)
    validate_dialogue_against_segments(dialogue, segment_file, registry)
    save_json_contract(dialogue_path, dialogue)

    return DialogueResult(
        dialogue_path=dialogue_path,
        dialogue=dialogue,
        accepted_count=len(dialogues),
        rejected_count=len(rejected),
        review_required=review_required,
        skipped=False,
    )


def _roster(registry: CharacterRegistry) -> tuple[str, ...]:
    """Return the character names the attribution prompt may use."""

    names: list[str] = []
    for character in registry.characters:
        names.append(character.name)
        names.extend(character.aliases)
    return tuple(names)
