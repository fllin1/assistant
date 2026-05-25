"""Cross-contract validator tests for LNVO v2."""

from __future__ import annotations

import pytest
from automations.ln_voice_over_v2.common.enums import (
    ArtifactKind,
    BeatType,
    PerspectiveStatus,
    ReviewStatus,
    StageStatus,
)
from automations.ln_voice_over_v2.common.errors import ContractValidationError
from automations.ln_voice_over_v2.pipeline.validators import (
    validate_dialogue_against_segments,
    validate_generation_against_scenes,
    validate_scenes_against_dialogue_and_segments,
)
from automations.ln_voice_over_v2.series.contracts import (
    Character,
    CharacterRegistry,
    VisualProfile,
)
from automations.ln_voice_over_v2.stages.dialogue.contracts import (
    DialogueChapter,
    DialogueRow,
    Perspective,
)
from automations.ln_voice_over_v2.stages.generation.contracts import (
    AudioBeat,
    AudioManifest,
    GenerationManifest,
    GenerationOutputs,
    VisualBeat,
    VisualTimeline,
)
from automations.ln_voice_over_v2.stages.scenes.contracts import (
    BackgroundChoice,
    Scene,
    SceneBeat,
    SceneDocument,
    Setting,
    VisibleCharacter,
)
from automations.ln_voice_over_v2.stages.transform.contracts import Segment, SegmentFile


def test_cross_contract_validators_accept_consistent_artifacts() -> None:
    """Consistent contracts pass every cross-contract validator."""
    validate_dialogue_against_segments(_dialogue(), _segments(), _registry())
    validate_scenes_against_dialogue_and_segments(
        _scenes(), _dialogue(), _segments(), _registry(), _visual_profile()
    )
    validate_generation_against_scenes(
        _generation_manifest(), _audio_manifest(), _visual_timeline(), _scenes()
    )


def test_dialogue_validator_reports_missing_segment_and_unknown_speaker() -> None:
    """Dialogue validation accumulates missing segment and registry problems."""
    dialogue = _dialogue(
        dialogues=(DialogueRow(segment_id="seg_999999", speaker="Mystery Student"),)
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_dialogue_against_segments(dialogue, _segments(), _registry())

    assert {problem.code for problem in exc_info.value.problems} == {
        "missing_segment",
        "unknown_speaker",
    }


def test_scene_validator_reports_missing_dialogue_and_visual_refs() -> None:
    """Scene validation catches broken dialogue and visual references."""
    scenes = _scenes(
        background=BackgroundChoice(asset_id="missing-background"),
        visible_characters=(
            VisibleCharacter(
                name="Horikita Suzune",
                image_id="missing-image",
                position="left",
            ),
        ),
        dialogue_segment_id="seg_000001",
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_scenes_against_dialogue_and_segments(
            scenes, _dialogue(), _segments(), _registry(), _visual_profile()
        )

    assert {problem.code for problem in exc_info.value.problems} >= {
        "missing_dialogue",
        "missing_dialogue_beat",
        "unknown_background",
        "unknown_character_image",
    }


def test_generation_validator_reports_missing_scene_beat() -> None:
    """Generation validation catches beat records not present in final scenes."""
    audio_manifest = _audio_manifest(beat_id="beat_9999")
    timeline = _visual_timeline(beat_id="beat_9999")

    with pytest.raises(ContractValidationError) as exc_info:
        validate_generation_against_scenes(
            _generation_manifest(), audio_manifest, timeline, _scenes()
        )

    assert [problem.code for problem in exc_info.value.problems].count("missing_scene_beat") == 2


def _segments() -> SegmentFile:
    return SegmentFile(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        segments=(
            Segment(segment_id="seg_000001", order=0, text="The hallway was quiet."),
            Segment(segment_id="seg_000002", order=1, text="What are you planning?"),
        ),
    )


def _dialogue(dialogues: tuple[DialogueRow, ...] | None = None) -> DialogueChapter:
    return DialogueChapter(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        status=ReviewStatus.ACCEPTED,
        review_required=False,
        perspective=Perspective(status=PerspectiveStatus.DETECTED, narrator="Ayanokouji Kiyotaka"),
        dialogues=dialogues
        if dialogues is not None
        else (DialogueRow(segment_id="seg_000002", speaker="Horikita Suzune"),),
    )


def _scenes(
    background: BackgroundChoice | None = None,
    visible_characters: tuple[VisibleCharacter, ...] | None = None,
    dialogue_segment_id: str = "seg_000002",
) -> SceneDocument:
    return SceneDocument(
        artifact_kind=ArtifactKind.SCENES_FINAL,
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        status=ReviewStatus.ACCEPTED,
        review_required=False,
        scenes=(
            Scene(
                scene_id="scene_0001",
                segment_ids=("seg_000001", "seg_000002"),
                summary="A hallway conversation.",
                setting=Setting(location="school hallway", time_of_day="afternoon", mood="tense"),
                background=background or BackgroundChoice(asset_id="school-hallway-day"),
                visible_characters=visible_characters
                if visible_characters is not None
                else (
                    VisibleCharacter(
                        name="Horikita Suzune",
                        image_id="horikita-serious",
                        position="left",
                    ),
                ),
                beats=(
                    SceneBeat(
                        beat_id="beat_0001",
                        beat_type=BeatType.NARRATION,
                        segment_ids=("seg_000001",),
                        spoken_text="The hallway was quiet.",
                    ),
                    SceneBeat(
                        beat_id="beat_0002",
                        beat_type=BeatType.DIALOGUE,
                        segment_id=dialogue_segment_id,
                        speaker="Horikita Suzune",
                        spoken_text="What are you planning?",
                    ),
                ),
            ),
        ),
    )


def _generation_manifest() -> GenerationManifest:
    return GenerationManifest(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        status=StageStatus.COMPLETE,
        scene_source="scenes/final/chapter_01.json",
        outputs=GenerationOutputs(
            audio="generation/chapter_01/audio.wav",
            audio_manifest="generation/chapter_01/audio_manifest.json",
            timeline="generation/chapter_01/timeline.json",
            video="generation/chapter_01/video.mp4",
        ),
        render_profile="default",
        voice_mapping="config/voice_mapping.json",
    )


def _audio_manifest(beat_id: str = "beat_0002") -> AudioManifest:
    return AudioManifest(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        beats=(
            AudioBeat(
                beat_id=beat_id,
                beat_type=BeatType.DIALOGUE,
                speaker="Horikita Suzune",
                voice_key="Horikita Suzune",
                engine="hume",
                voice_id="voice-1",
                cache_key="sha256-abc",
                stem="generation/chapter_01/stems/beat_0002.wav",
                start_ms=0,
                duration_ms=1000,
                end_ms=1000,
            ),
        ),
    )


def _visual_timeline(beat_id: str = "beat_0002") -> VisualTimeline:
    return VisualTimeline(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        beats=(
            VisualBeat(
                beat_id=beat_id,
                start_ms=0,
                end_ms=1000,
                background="school-hallway-day",
                visible_characters=("horikita-serious",),
            ),
        ),
    )


def _registry() -> CharacterRegistry:
    return CharacterRegistry(
        characters=(
            Character(name="Ayanokouji Kiyotaka", aliases=("Ayanokouji",), role="main"),
            Character(name="Horikita Suzune", aliases=("Horikita",), role="main"),
        )
    )


def _visual_profile() -> VisualProfile:
    return VisualProfile(
        profile_id="default",
        backgrounds={"school-hallway-day": {"path": "assets/backgrounds/hallway.png"}},
        character_images={"horikita-serious": {"path": "assets/characters/horikita.png"}},
    )
