"""Contract model tests for LNVO v2."""

from __future__ import annotations

from pathlib import Path

import pytest
from automations.ln_voice_over_v2.common.enums import (
    ArtifactKind,
    BeatType,
    MediaType,
    PerspectiveStatus,
    ReviewStatus,
    StageStatus,
)
from automations.ln_voice_over_v2.common.json_io import load_json_contract, save_json_contract
from automations.ln_voice_over_v2.common.paths import (
    dialogue_chapter_path,
    generation_dir,
    prepared_volume_path,
    scene_document_path,
    segment_file_path,
    volume_index_path,
)
from automations.ln_voice_over_v2.pipeline.contracts import PipelineRun, StageResult
from automations.ln_voice_over_v2.series.contracts import (
    Character,
    CharacterRegistry,
    NarrationProfile,
    RenderProfile,
    StoryProfile,
    VisualProfile,
    VoiceMapping,
    VoiceMappingEntry,
)
from automations.ln_voice_over_v2.stages.dialogue.contracts import (
    DialogueChapter,
    DialogueRow,
    Perspective,
    RejectedCandidate,
)
from automations.ln_voice_over_v2.stages.generation.contracts import (
    AudioBeat,
    AudioManifest,
    GenerationManifest,
    GenerationOutputs,
    VisualBeat,
    VisualTimeline,
)
from automations.ln_voice_over_v2.stages.prepare.contracts import (
    PreparedMedia,
    PreparedTextUnit,
    PreparedVolume,
)
from automations.ln_voice_over_v2.stages.scenes.contracts import (
    BackgroundChoice,
    Scene,
    SceneBeat,
    SceneDocument,
    Setting,
    VisibleCharacter,
)
from automations.ln_voice_over_v2.stages.transform.contracts import (
    ChapterIndexEntry,
    Segment,
    SegmentFile,
    VolumeIndex,
)
from pydantic import ValidationError


def test_persisted_artifacts_round_trip() -> None:
    """Every persisted artifact has a strict JSON round trip."""
    for artifact in _persisted_artifacts():
        payload = artifact.model_dump_json()
        assert type(artifact).model_validate_json(payload) == artifact


def test_series_profiles_round_trip() -> None:
    """Series-level config contracts round-trip as JSON."""
    profiles = [
        StoryProfile(profile_id="classroom", display_name="Classroom", rules={}),
        _registry(),
        VoiceMapping(
            entries={
                "Horikita Suzune": VoiceMappingEntry(
                    engine="hume", voice_id="voice-1", params={"style": "cool"}
                )
            }
        ),
        NarrationProfile(profile_id="default", settings={"max_words": 80}),
        _visual_profile(),
        RenderProfile(
            profile_id="default",
            width=1920,
            height=1080,
            fps=30,
            audio_format="wav",
            video_format="mp4",
        ),
    ]
    for profile in profiles:
        assert type(profile).model_validate_json(profile.model_dump_json()) == profile


def test_unknown_keys_are_rejected() -> None:
    """Public contracts reject unknown JSON keys."""
    payload = _prepared_volume().model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        PreparedVolume.model_validate(payload)


def test_invalid_enum_value_is_rejected() -> None:
    """Enum fields reject unsupported values."""
    payload = _dialogue_chapter().model_dump(mode="json")
    payload["status"] = "done"

    with pytest.raises(ValidationError):
        DialogueChapter.model_validate(payload)


def test_invalid_id_is_rejected() -> None:
    """Canonical ID formats are enforced."""
    with pytest.raises(ValidationError):
        Segment(segment_id="segment_1", order=0, text="Bad id")


@pytest.mark.parametrize(
    "path", ["/absolute/file.txt", "../raw.txt", "raw\\file.txt", "raw//file.txt"]
)
def test_invalid_artifact_path_is_rejected(path: str) -> None:
    """Artifact-relative paths reject absolute, traversal, and non-POSIX shapes."""
    with pytest.raises(ValidationError):
        PreparedTextUnit(
            text_unit_id="unit_000001",
            order=0,
            text="Text",
            source_path=path,
            source_locator={},
        )


def test_json_io_round_trip(tmp_path: Path) -> None:
    """JSON helpers persist and reload contracts."""
    path = tmp_path / "prepared" / "volume.json"
    expected = _prepared_volume()

    save_json_contract(path, expected)

    assert load_json_contract(path, PreparedVolume) == expected


def test_path_helpers_match_contract_layout(tmp_path: Path) -> None:
    """Path helpers resolve the documented runtime layout."""
    root = tmp_path / "projects"

    assert (
        prepared_volume_path(root, "series-one", "v1")
        == root / "series-one/v1/prepared/volume.json"
    )
    assert volume_index_path(root, "series-one", "v1") == root / "series-one/v1/volume_index.json"
    assert (
        segment_file_path(root, "series-one", "v1", "chapter_01")
        == root / "series-one/v1/segments/chapter_01.json"
    )
    assert (
        dialogue_chapter_path(root, "series-one", "v1", "chapter_01")
        == root / "series-one/v1/dialogue/chapter_01.json"
    )
    assert (
        scene_document_path(root, "series-one", "v1", "chapter_01", ArtifactKind.SCENES_FINAL)
        == root / "series-one/v1/scenes/final/chapter_01.json"
    )
    assert generation_dir(root, "series-one", "v1", "chapter_01") == root / (
        "series-one/v1/generation/chapter_01"
    )


def test_pipeline_contracts_have_no_execution_behavior() -> None:
    """The skeleton exposes orchestration records, not runnable stage code."""
    result = StageResult(stage="prepare", status="pending", artifacts=("prepared/volume.json",))
    run = PipelineRun(series="series-one", volume="v1", stages=(result,))

    assert run.status == StageStatus.PENDING
    assert result.artifacts == ("prepared/volume.json",)


def _prepared_volume() -> PreparedVolume:
    return PreparedVolume(
        series="series-one",
        volume="v1",
        story_profile="classroom",
        source_profile="pdf-ocr",
        text_units=(
            PreparedTextUnit(
                text_unit_id="unit_000001",
                order=0,
                text="The hallway was quiet.",
                source_path="source/pages/page-001.txt",
                source_locator={"page": 1},
            ),
        ),
        media=(
            PreparedMedia(
                media_id="page-001",
                order=0,
                media_type=MediaType.PAGE_IMAGE,
                path="prepared/media/page-001.png",
                source_path="source/pages/page-001.png",
            ),
        ),
    )


def _segment_file() -> SegmentFile:
    return SegmentFile(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        segments=(
            Segment(
                segment_id="seg_000001",
                order=0,
                text="The hallway was quiet.",
                source_unit_ids=("unit_000001",),
            ),
            Segment(segment_id="seg_000002", order=1, text="What are you planning?"),
        ),
    )


def _volume_index() -> VolumeIndex:
    return VolumeIndex(
        series="series-one",
        volume="v1",
        chapters=(
            ChapterIndexEntry(
                chapter_id="chapter_01",
                order=0,
                segments_file="segments/chapter_01.json",
                display_name="Chapter 1",
            ),
        ),
    )


def _dialogue_chapter() -> DialogueChapter:
    return DialogueChapter(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        status=ReviewStatus.ACCEPTED,
        review_required=False,
        perspective=Perspective(status=PerspectiveStatus.DETECTED, narrator="Ayanokouji Kiyotaka"),
        dialogues=(DialogueRow(segment_id="seg_000002", speaker="Horikita Suzune"),),
        rejected_candidates=(
            RejectedCandidate(segment_id="seg_000001", reason="Narration, not spoken dialogue."),
        ),
        review_notes=(),
    )


def _scene_document() -> SceneDocument:
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
                summary="A quiet hallway conversation.",
                setting=Setting(location="school hallway", time_of_day="afternoon", mood="tense"),
                background=BackgroundChoice(asset_id="school-hallway-day"),
                visible_characters=(
                    VisibleCharacter(
                        name="Horikita Suzune",
                        image_id="horikita-serious",
                        position="left",
                        expression="serious",
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
                        segment_id="seg_000002",
                        speaker="Horikita Suzune",
                        spoken_text="What are you planning?",
                        bubble_text="What are you planning?",
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


def _audio_manifest() -> AudioManifest:
    return AudioManifest(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        beats=(
            AudioBeat(
                beat_id="beat_0002",
                beat_type=BeatType.DIALOGUE,
                speaker="Horikita Suzune",
                voice_key="Horikita Suzune",
                engine="hume",
                voice_id="voice-1",
                cache_key="sha256-abc",
                stem="generation/chapter_01/stems/beat_0002.wav",
                start_ms=0,
                duration_ms=1800,
                end_ms=1800,
            ),
        ),
    )


def _visual_timeline() -> VisualTimeline:
    return VisualTimeline(
        series="series-one",
        volume="v1",
        chapter_id="chapter_01",
        beats=(
            VisualBeat(
                beat_id="beat_0002",
                start_ms=0,
                end_ms=1800,
                background="school-hallway-day",
                visible_characters=("horikita-serious",),
                bubble_text="What are you planning?",
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


def _persisted_artifacts() -> list[object]:
    return [
        _prepared_volume(),
        _volume_index(),
        _segment_file(),
        _dialogue_chapter(),
        _scene_document(),
        _generation_manifest(),
        _audio_manifest(),
        _visual_timeline(),
    ]
