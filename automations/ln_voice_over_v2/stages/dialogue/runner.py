"""Run dialogue attribution for a prepared chapter."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
from .agent import (
    DEFAULT_DIALOGUE_TIMEOUT_SECONDS,
    DialogueProposal,
    run_codex_dialogue,
)
from .chunking import DEFAULT_MAX_CANDIDATES_PER_CHUNK, attribute_with_chunking
from .config import (
    load_character_registry,
    load_story_profile,
    resolve_story_profile_path,
)
from .context import ChapterPayload, build_chapter_payload
from .contracts import DialogueChapter, DialogueRow, Perspective, RejectedCandidate
from .names import canonical_narrator, canonical_speaker, unregistered_speaker_raw
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
    timeout_seconds: int = DEFAULT_DIALOGUE_TIMEOUT_SECONDS
    max_candidates_per_chunk: int = DEFAULT_MAX_CANDIDATES_PER_CHUNK


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
                    message=(
                        f"{config.chapter_id!r} is not in the volume index; "
                        f"available: {', '.join(sorted(chapter_ids))}"
                    ),
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
        roster = _roster(registry)

        def attribute_fn(payload: ChapterPayload) -> DialogueProposal:
            def attribute_chunk(chunk: ChapterPayload) -> DialogueProposal:
                return run_codex_dialogue(
                    build_prompt(chunk, roster),
                    timeout_seconds=config.timeout_seconds,
                )

            return attribute_with_chunking(
                payload,
                attribute_chunk=attribute_chunk,
                max_candidates_per_chunk=config.max_candidates_per_chunk,
            )

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
            speaker = canonical_speaker(
                decision.speaker_raw,
                registry,
                narrator=narrator,
            )
            speaker_raw = None
            speaker_gender = "unknown"
            if speaker == UNKNOWN_SPEAKER:
                speaker_raw = unregistered_speaker_raw(
                    decision.speaker_raw,
                    registry,
                    narrator=narrator,
                )
                if speaker_raw is not None:
                    speaker_gender = decision.speaker_gender
            dialogues.append(
                DialogueRow(
                    segment_id=segment_id,
                    speaker=speaker,
                    speaker_raw=speaker_raw,
                    speaker_gender=speaker_gender,
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


@dataclass(frozen=True)
class DialogueVolumeConfig:
    """Configuration for running dialogue attribution across a whole volume."""

    series: SeriesId
    volume: VolumeId
    data_root: Path = paths.DEFAULT_PROJECT_DATA_ROOT
    force: bool = False
    workers: int = 4
    timeout_seconds: int = DEFAULT_DIALOGUE_TIMEOUT_SECONDS
    max_candidates_per_chunk: int = DEFAULT_MAX_CANDIDATES_PER_CHUNK


@dataclass(frozen=True)
class ChapterOutcome:
    """Outcome of one chapter within a volume dialogue run."""

    chapter_id: ChapterId
    result: DialogueResult | None = None
    error: str | None = None


@dataclass(frozen=True)
class DialogueVolumeResult:
    """Aggregate result of a volume dialogue run, in volume order."""

    outcomes: tuple[ChapterOutcome, ...]

    @property
    def written(self) -> int:
        """Return the number of chapters (re)generated this run."""
        return sum(
            1
            for outcome in self.outcomes
            if outcome.result is not None and not outcome.result.skipped
        )

    @property
    def skipped(self) -> int:
        """Return the number of chapters skipped because their file already existed."""
        return sum(
            1 for outcome in self.outcomes if outcome.result is not None and outcome.result.skipped
        )

    @property
    def failed(self) -> int:
        """Return the number of chapters that raised during attribution."""
        return sum(1 for outcome in self.outcomes if outcome.error is not None)


def run_dialogue_volume(
    config: DialogueVolumeConfig,
    *,
    attribute_fn: AttributeFn | None = None,
) -> DialogueVolumeResult:
    """Run dialogue attribution for every chapter in a volume, in parallel.

    Each chapter is processed by `run_dialogue`; an existing dialogue file is
    skipped unless `config.force`. A per-chapter failure is isolated and
    reported rather than aborting the whole volume.

    Args:
        config: Volume-level dialogue configuration.
        attribute_fn: Optional attribution seam shared by every chapter.

    Returns:
        Per-chapter outcomes in volume order.
    """
    volume_index = load_json_contract(
        paths.volume_index_path(config.data_root, config.series, config.volume),
        VolumeIndex,
    )
    chapter_ids = [chapter.chapter_id for chapter in volume_index.chapters]
    logger.info(
        "dialogue: dispatching %d chapter(s) over %d worker(s)",
        len(chapter_ids),
        config.workers,
    )

    def _run_one(chapter_id: ChapterId) -> ChapterOutcome:
        chapter_config = DialogueConfig(
            series=config.series,
            volume=config.volume,
            chapter_id=chapter_id,
            data_root=config.data_root,
            force=config.force,
            timeout_seconds=config.timeout_seconds,
            max_candidates_per_chunk=config.max_candidates_per_chunk,
        )
        # Each chapter is a separate external model call; isolate a per-chapter
        # failure so one bad chapter does not abort the rest of the volume.
        try:
            result = run_dialogue(chapter_config, attribute_fn=attribute_fn)
        except Exception as exc:
            logger.warning("dialogue: chapter %s failed: %s", chapter_id, exc)
            return ChapterOutcome(chapter_id=chapter_id, error=str(exc))
        return ChapterOutcome(chapter_id=chapter_id, result=result)

    with ThreadPoolExecutor(max_workers=max(1, config.workers)) as executor:
        outcomes = tuple(executor.map(_run_one, chapter_ids))
    return DialogueVolumeResult(outcomes=outcomes)


def _roster(registry: CharacterRegistry) -> tuple[str, ...]:
    """Return the character names the attribution prompt may use."""

    names: list[str] = []
    for character in registry.characters:
        names.append(character.name)
        names.extend(character.aliases)
    return tuple(names)
