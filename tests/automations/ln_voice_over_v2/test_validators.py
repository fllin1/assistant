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
    validate_transform_against_prepared,
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
from automations.ln_voice_over_v2.stages.prepare.contracts import (
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
from automations.ln_voice_over_v2.stages.transform.validation import (
    validate_transform_artifacts,
)


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


def test_validate_transform_artifacts_accepts_valid_index_and_segments() -> None:
    """Valid transform artifacts pass stage-local validation."""
    validate_transform_artifacts(_transform_index(chapter_count=2), _transform_segment_files(2))


def test_validate_transform_artifacts_reports_duplicate_segment_order() -> None:
    """Duplicate segment orders are reported within a chapter."""
    segment_files = (
        _transform_segment_file(
            segments=(
                _transform_segment("seg_000001", 0, "First", ("unit_000000",)),
                _transform_segment("seg_000002", 0, "Second", ("unit_000001",)),
            )
        ),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_artifacts(_transform_index(), segment_files)

    assert "duplicate_order" in _codes(exc_info.value)


def test_validate_transform_artifacts_reports_gapped_segment_order() -> None:
    """Non-dense segment orders are reported within a chapter."""
    segment_files = (
        _transform_segment_file(
            segments=(
                _transform_segment("seg_000001", 0, "First", ("unit_000000",)),
                _transform_segment("seg_000002", 2, "Second", ("unit_000001",)),
            )
        ),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_artifacts(_transform_index(), segment_files)

    assert "nonconsecutive_order" in _codes(exc_info.value)


def test_validate_transform_artifacts_reports_bad_segments_file() -> None:
    """Chapter entries must point at their canonical segment file path."""
    index = _transform_index(
        chapters=(
            ChapterIndexEntry(
                chapter_id="chapter_01",
                order=0,
                segments_file="segments/wrong.json",
                display_name="Chapter 1",
            ),
        )
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_artifacts(index, _transform_segment_files())

    assert _codes(exc_info.value) == {"bad_segments_file"}


def test_validate_transform_artifacts_reports_empty_display_name() -> None:
    """Whitespace-only chapter display names are rejected."""
    index = _transform_index(
        chapters=(
            ChapterIndexEntry(
                chapter_id="chapter_01",
                order=0,
                segments_file="segments/chapter_01.json",
                display_name=" ",
            ),
        )
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_artifacts(index, _transform_segment_files())

    assert _codes(exc_info.value) == {"empty_display_name"}


def test_validate_transform_artifacts_reports_nondense_segment_id() -> None:
    """Segment ids must start at seg_000001 and be dense within each chapter."""
    segment_files = (
        _transform_segment_file(
            segments=(_transform_segment("seg_000002", 0, "First", ("unit_000000",)),)
        ),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_artifacts(_transform_index(), segment_files)

    assert _codes(exc_info.value) == {"nonconsecutive_segment_id"}


def test_validate_transform_against_prepared_accepts_matching_artifacts() -> None:
    """Transform artifacts pass when they align with the prepared volume."""
    validate_transform_against_prepared(
        _transform_index(),
        _transform_segment_files(),
        _prepared_volume_for_transform(),
    )


def test_validate_transform_against_prepared_reports_unknown_source_unit_id() -> None:
    """Every segment source unit must exist in the prepared volume."""
    segment_files = (
        _transform_segment_file(
            segments=(
                _transform_segment("seg_000001", 0, "First", ("unit_000000", "unit_999999")),
            )
        ),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_against_prepared(
            _transform_index(),
            segment_files,
            _prepared_volume_for_transform(),
        )

    assert "missing_text_unit" in _codes(exc_info.value)


def test_validate_transform_against_prepared_reports_missing_coverage() -> None:
    """Non-empty prepared text units must be covered by at least one segment."""
    segment_files = (
        _transform_segment_file(
            segments=(_transform_segment("seg_000001", 0, "First", ("unit_000000",)),)
        ),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_against_prepared(
            _transform_index(),
            segment_files,
            _prepared_volume_for_transform(),
        )

    assert "missing_coverage" in _codes(exc_info.value)


def test_validate_transform_against_prepared_exempts_illustration_only_text_units() -> None:
    """Empty non-review text units do not require segment coverage."""
    prepared = _prepared_volume_for_transform(
        text_units=(
            _prepared_text_unit("unit_000000", 0, "First"),
            _prepared_text_unit("unit_000001", 1, ""),
        )
    )
    segment_files = (
        _transform_segment_file(
            segments=(_transform_segment("seg_000001", 0, "First", ("unit_000000",)),)
        ),
    )

    validate_transform_against_prepared(_transform_index(), segment_files, prepared)


def test_validate_transform_against_prepared_requires_needs_review_coverage() -> None:
    """Needs-review text units require coverage even when their text is empty."""
    prepared = _prepared_volume_for_transform(
        text_units=(
            _prepared_text_unit("unit_000000", 0, "First"),
            _prepared_text_unit("unit_000001", 1, "", needs_review=True),
        )
    )
    segment_files = (
        _transform_segment_file(
            segments=(_transform_segment("seg_000001", 0, "First", ("unit_000000",)),)
        ),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_against_prepared(_transform_index(), segment_files, prepared)

    assert _codes(exc_info.value) == {"missing_coverage"}


def test_validate_transform_against_prepared_reports_chapter_count_mismatch() -> None:
    """The volume index and segment file tuple must have matching chapter counts."""
    with pytest.raises(ContractValidationError) as exc_info:
        validate_transform_against_prepared(
            _transform_index(chapter_count=2),
            _transform_segment_files(1),
            _prepared_volume_for_transform(),
        )

    assert "chapter_count_mismatch" in _codes(exc_info.value)


def _transform_index(
    *,
    chapter_count: int = 1,
    chapters: tuple[ChapterIndexEntry, ...] | None = None,
) -> VolumeIndex:
    return VolumeIndex(
        series="series-one",
        volume="v1",
        chapters=chapters
        if chapters is not None
        else tuple(
            ChapterIndexEntry(
                chapter_id=f"chapter_{index + 1:02d}",
                order=index,
                segments_file=f"segments/chapter_{index + 1:02d}.json",
                display_name=f"Chapter {index + 1}",
            )
            for index in range(chapter_count)
        ),
    )


def _transform_segment_files(chapter_count: int = 1) -> tuple[SegmentFile, ...]:
    return tuple(
        _transform_segment_file(
            chapter_id=f"chapter_{index + 1:02d}",
            segments=(
                _transform_segment(
                    "seg_000001",
                    0,
                    f"Chapter {index + 1} first segment.",
                    ("unit_000000",),
                ),
                _transform_segment(
                    "seg_000002",
                    1,
                    f"Chapter {index + 1} second segment.",
                    ("unit_000001",),
                ),
            ),
        )
        for index in range(chapter_count)
    )


def _transform_segment_file(
    *,
    chapter_id: str = "chapter_01",
    segments: tuple[Segment, ...],
) -> SegmentFile:
    return SegmentFile(
        series="series-one",
        volume="v1",
        chapter_id=chapter_id,
        segments=segments,
    )


def _transform_segment(
    segment_id: str,
    order: int,
    text: str,
    source_unit_ids: tuple[str, ...],
) -> Segment:
    return Segment(
        segment_id=segment_id,
        order=order,
        text=text,
        source_unit_ids=source_unit_ids,
        parser_hints={"quote_candidate": False},
    )


def _prepared_volume_for_transform(
    *,
    text_units: tuple[PreparedTextUnit, ...] | None = None,
) -> PreparedVolume:
    return PreparedVolume(
        series="series-one",
        volume="v1",
        story_profile="default",
        source_profile="pdf-llm-ocr",
        text_units=text_units
        if text_units is not None
        else (
            _prepared_text_unit("unit_000000", 0, "First"),
            _prepared_text_unit("unit_000001", 1, "Second"),
        ),
    )


def _prepared_text_unit(
    text_unit_id: str,
    order: int,
    text: str,
    *,
    needs_review: bool = False,
) -> PreparedTextUnit:
    return PreparedTextUnit(
        text_unit_id=text_unit_id,
        order=order,
        text=text,
        source_path=f"source/pages/{order + 1:03d}.txt",
        source_locator={"page": order + 1},
        needs_review=needs_review,
    )


def _codes(error: ContractValidationError) -> set[str]:
    return {problem.code for problem in error.problems}
