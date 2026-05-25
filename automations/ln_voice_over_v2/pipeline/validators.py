"""Cross-contract validators for LNVO v2."""

from __future__ import annotations

from ..common.enums import BeatType, PerspectiveStatus
from ..common.errors import ContractValidationError, ValidationProblem
from ..series.contracts import CharacterRegistry, VisualProfile
from ..stages.dialogue.contracts import DialogueChapter
from ..stages.generation.contracts import AudioManifest, GenerationManifest, VisualTimeline
from ..stages.scenes.contracts import SceneDocument
from ..stages.transform.contracts import SegmentFile

UNKNOWN_SPEAKER = "Unknown"


def validate_dialogue_against_segments(
    dialogue: DialogueChapter,
    segments: SegmentFile,
    registry: CharacterRegistry,
) -> None:
    """Validate dialogue references against segment and character contracts."""
    problems: list[ValidationProblem] = []
    _same_chapter(dialogue.chapter_id, segments.chapter_id, "dialogue.chapter_id", problems)

    segment_ids = {segment.segment_id for segment in segments.segments}
    seen_dialogue_ids: set[str] = set()
    for index, row in enumerate(dialogue.dialogues):
        path = f"dialogues[{index}]"
        if row.segment_id not in segment_ids:
            problems.append(_problem("missing_segment", f"unknown segment {row.segment_id}", path))
        if row.segment_id in seen_dialogue_ids:
            problems.append(
                _problem("duplicate_dialogue", f"duplicate segment {row.segment_id}", path)
            )
        seen_dialogue_ids.add(row.segment_id)
        _validate_speaker(row.speaker, registry, f"{path}.speaker", problems)

    for index, candidate in enumerate(dialogue.rejected_candidates):
        if candidate.segment_id not in segment_ids:
            problems.append(
                _problem(
                    "missing_segment",
                    f"unknown segment {candidate.segment_id}",
                    f"rejected_candidates[{index}]",
                )
            )

    if dialogue.perspective.status == PerspectiveStatus.DETECTED:
        narrator = dialogue.perspective.narrator
        if narrator is not None and not registry.has_character(narrator):
            problems.append(
                _problem(
                    "unknown_narrator",
                    f"unknown narrator {narrator}",
                    "perspective.narrator",
                )
            )

    _raise_if_problems(problems)


def validate_scenes_against_dialogue_and_segments(
    scenes: SceneDocument,
    dialogue: DialogueChapter,
    segments: SegmentFile,
    registry: CharacterRegistry,
    visual_profile: VisualProfile,
) -> None:
    """Validate scene references against dialogue, segment, character, and visual contracts."""
    problems: list[ValidationProblem] = []
    _same_chapter(scenes.chapter_id, dialogue.chapter_id, "scenes.chapter_id", problems)
    _same_chapter(scenes.chapter_id, segments.chapter_id, "scenes.chapter_id", problems)

    segment_ids = {segment.segment_id for segment in segments.segments}
    dialogue_ids = {row.segment_id for row in dialogue.dialogues}
    dialogue_beat_ids: set[str] = set()
    scene_beat_ids: set[str] = set()

    for scene_index, scene in enumerate(scenes.scenes):
        scene_path = f"scenes[{scene_index}]"
        for segment_id in scene.segment_ids:
            if segment_id not in segment_ids:
                problems.append(
                    _problem("missing_segment", f"unknown segment {segment_id}", scene_path)
                )

        background_id = scene.background.asset_id
        if background_id is not None and background_id not in visual_profile.backgrounds:
            problems.append(
                _problem(
                    "unknown_background",
                    f"unknown background {background_id}",
                    f"{scene_path}.background.asset_id",
                )
            )

        for character_index, character in enumerate(scene.visible_characters):
            character_path = f"{scene_path}.visible_characters[{character_index}]"
            if not registry.has_character(character.name):
                problems.append(
                    _problem(
                        "unknown_character",
                        f"unknown character {character.name}",
                        character_path,
                    )
                )
            if character.image_id not in visual_profile.character_images:
                problems.append(
                    _problem(
                        "unknown_character_image",
                        f"unknown character image {character.image_id}",
                        f"{character_path}.image_id",
                    )
                )

        for beat_index, beat in enumerate(scene.beats):
            beat_path = f"{scene_path}.beats[{beat_index}]"
            scene_beat_ids.add(beat.beat_id)
            if beat.segment_id is not None and beat.segment_id not in segment_ids:
                problems.append(
                    _problem("missing_segment", f"unknown segment {beat.segment_id}", beat_path)
                )
            for segment_id in beat.segment_ids:
                if segment_id not in segment_ids:
                    problems.append(
                        _problem("missing_segment", f"unknown segment {segment_id}", beat_path)
                    )
            if beat.beat_type == BeatType.DIALOGUE:
                if beat.segment_id not in dialogue_ids:
                    problems.append(
                        _problem(
                            "missing_dialogue",
                            f"unknown dialogue segment {beat.segment_id}",
                            beat_path,
                        )
                    )
                else:
                    dialogue_beat_ids.add(beat.segment_id)
            if beat.speaker is not None:
                _validate_speaker(beat.speaker, registry, f"{beat_path}.speaker", problems)

    for dialogue_id in dialogue_ids - dialogue_beat_ids:
        problems.append(
            _problem(
                "missing_dialogue_beat",
                f"dialogue segment {dialogue_id} is not represented by a dialogue beat",
                "scenes",
            )
        )

    if not scene_beat_ids and scenes.scenes:
        problems.append(
            _problem("missing_beats", "scene document has scenes but no beats", "scenes")
        )

    _raise_if_problems(problems)


def validate_generation_against_scenes(
    manifest: GenerationManifest,
    audio_manifest: AudioManifest,
    timeline: VisualTimeline,
    scenes: SceneDocument,
) -> None:
    """Validate generation records against final scene beats."""
    problems: list[ValidationProblem] = []
    _same_chapter(manifest.chapter_id, scenes.chapter_id, "manifest.chapter_id", problems)
    _same_chapter(
        audio_manifest.chapter_id, scenes.chapter_id, "audio_manifest.chapter_id", problems
    )
    _same_chapter(timeline.chapter_id, scenes.chapter_id, "timeline.chapter_id", problems)

    scene_beat_ids = {beat.beat_id for scene in scenes.scenes for beat in scene.beats}
    for index, beat in enumerate(audio_manifest.beats):
        if beat.beat_id not in scene_beat_ids:
            problems.append(
                _problem(
                    "missing_scene_beat",
                    f"audio beat {beat.beat_id} does not exist in scenes",
                    f"audio_manifest.beats[{index}]",
                )
            )
        if beat.end_ms != beat.start_ms + beat.duration_ms:
            problems.append(
                _problem(
                    "invalid_timing",
                    "end_ms must equal start_ms + duration_ms",
                    f"audio_manifest.beats[{index}]",
                )
            )

    for index, beat in enumerate(timeline.beats):
        if beat.beat_id not in scene_beat_ids:
            problems.append(
                _problem(
                    "missing_scene_beat",
                    f"visual beat {beat.beat_id} does not exist in scenes",
                    f"timeline.beats[{index}]",
                )
            )
        if beat.end_ms < beat.start_ms:
            problems.append(
                _problem(
                    "invalid_timing",
                    "end_ms must be >= start_ms",
                    f"timeline.beats[{index}]",
                )
            )

    _raise_if_problems(problems)


def _same_chapter(left: str, right: str, path: str, problems: list[ValidationProblem]) -> None:
    if left != right:
        problems.append(_problem("chapter_mismatch", f"{left} does not match {right}", path))


def _validate_speaker(
    speaker: str, registry: CharacterRegistry, path: str, problems: list[ValidationProblem]
) -> None:
    if speaker != UNKNOWN_SPEAKER and not registry.has_character(speaker):
        problems.append(_problem("unknown_speaker", f"unknown speaker {speaker}", path))


def _problem(code: str, message: str, path: str) -> ValidationProblem:
    return ValidationProblem(code=code, message=message, path=path)


def _raise_if_problems(problems: list[ValidationProblem]) -> None:
    if problems:
        raise ContractValidationError(problems)
