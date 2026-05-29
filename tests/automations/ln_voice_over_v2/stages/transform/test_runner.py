"""Runner tests for the transform stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from automations.ln_voice_over_v2.common import paths
from automations.ln_voice_over_v2.common.errors import (
    ContractValidationError,
    ValidationProblem,
)
from automations.ln_voice_over_v2.common.json_io import load_json_contract, save_json_contract
from automations.ln_voice_over_v2.stages.prepare.contracts import (
    PreparedTextUnit,
    PreparedVolume,
)
from automations.ln_voice_over_v2.stages.transform.__main__ import main
from automations.ln_voice_over_v2.stages.transform.chapters import (
    PACKAGED_DEFAULT_STORY_PROFILE,
)
from automations.ln_voice_over_v2.stages.transform.contracts import SegmentFile, VolumeIndex
from automations.ln_voice_over_v2.stages.transform.runner import (
    TransformConfig,
    run_transform,
)


def test_happy_path_writes_index_and_segments(tmp_path: Path) -> None:
    series = "series-one"
    volume = "v1"
    _write_prepared_volume(tmp_path, series, volume, _default_units())

    result = run_transform(TransformConfig(series=series, volume=volume, data_root=tmp_path))

    expected_index_path = tmp_path / series / volume / "volume_index.json"
    assert result.volume_index_path == expected_index_path
    assert expected_index_path.is_file()
    assert (tmp_path / series / volume / "segments" / "chapter_00.json").is_file()
    assert (tmp_path / series / volume / "segments" / "chapter_02.json").is_file()
    assert (tmp_path / series / volume / "segments" / "chapter_03.json").is_file()
    assert result.chapter_count == 3
    assert result.segment_count == sum(
        len(segment_file.segments)
        for segment_file in (
            load_json_contract(
                paths.segment_file_path(tmp_path, series, volume, chapter.chapter_id),
                SegmentFile,
            )
            for chapter in result.volume_index.chapters
        )
    )
    assert result.story_profile_source == PACKAGED_DEFAULT_STORY_PROFILE

    written_index = load_json_contract(expected_index_path, VolumeIndex)
    assert [chapter.display_name for chapter in written_index.chapters] == [
        "Prologue",
        "Chapter 2",
        "Epilogue",
    ]


def test_cross_validator_runs_before_any_file_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = "series-one"
    volume = "v1"
    _write_prepared_volume(tmp_path, series, volume, _default_units())

    def fail_cross_validation(*_args: object) -> None:
        raise ContractValidationError(
            [ValidationProblem(code="test_fail", message="forced", path="test")]
        )

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.transform.runner.validate_transform_against_prepared",
        fail_cross_validation,
    )

    with pytest.raises(ContractValidationError):
        run_transform(TransformConfig(series=series, volume=volume, data_root=tmp_path))

    volume_index_path = paths.volume_index_path(tmp_path, series, volume)
    segments_dir = tmp_path / series / volume / "segments"
    assert not volume_index_path.exists()
    assert not segments_dir.exists() or not any(segments_dir.iterdir())


def test_force_wipes_pre_existing_files(tmp_path: Path) -> None:
    series = "series-one"
    volume = "v1"
    _write_prepared_volume(tmp_path, series, volume, _default_units())
    stale_segment = tmp_path / series / volume / "segments" / "chapter_99.json"
    stale_segment.parent.mkdir(parents=True)
    stale_segment.write_text('{"stale": true}', encoding="utf-8")
    volume_index_path = paths.volume_index_path(tmp_path, series, volume)
    volume_index_path.write_text('{"stale": true}', encoding="utf-8")

    run_transform(TransformConfig(series=series, volume=volume, data_root=tmp_path, force=True))

    assert not stale_segment.exists()
    assert volume_index_path.is_file()
    assert paths.segment_file_path(tmp_path, series, volume, "chapter_00").is_file()


def test_determinism(tmp_path: Path) -> None:
    series = "series-one"
    volume = "v1"
    _write_prepared_volume(tmp_path, series, volume, _default_units())

    first = run_transform(TransformConfig(series=series, volume=volume, data_root=tmp_path))
    first_bytes = _read_transform_bytes(first.segments_dir, first.volume_index_path)

    second = run_transform(TransformConfig(series=series, volume=volume, data_root=tmp_path))
    second_bytes = _read_transform_bytes(second.segments_dir, second.volume_index_path)

    assert second_bytes == first_bytes


def test_per_series_override_wins_over_packaged_template(tmp_path: Path) -> None:
    series = "series-one"
    volume = "v1"
    override_path = tmp_path / series / "config" / "story_profile.json"
    override_path.parent.mkdir(parents=True)
    override_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "default",
                "display_name": "Override Story Profile",
                "rules": {
                    "chapter_headings": ["^### Section\\b"],
                    "subchapters": False,
                },
            }
        ),
        encoding="utf-8",
    )
    _write_prepared_volume(
        tmp_path,
        series,
        volume,
        (
            _unit(0, "### Section\nOpening."),
            _unit(1, "### Section\nMore."),
        ),
    )

    result = run_transform(TransformConfig(series=series, volume=volume, data_root=tmp_path))

    assert result.story_profile_source == override_path


def test_cli_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    series = "series-one"
    volume = "v1"
    _write_prepared_volume(tmp_path, series, volume, _default_units())
    expected_path = paths.volume_index_path(tmp_path, series, volume)

    exit_code = main(
        [
            "--series",
            series,
            "--volume",
            volume,
            "--data-root",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(expected_path) in captured.out


def _read_transform_bytes(segments_dir: Path, volume_index_path: Path) -> dict[str, bytes]:
    return {
        "volume_index.json": volume_index_path.read_bytes(),
        **{path.name: path.read_bytes() for path in sorted(segments_dir.glob("*.json"))},
    }


def _write_prepared_volume(
    data_root: Path,
    series: str,
    volume: str,
    text_units: tuple[PreparedTextUnit, ...],
) -> None:
    save_json_contract(
        paths.prepared_volume_path(data_root, series, volume),
        PreparedVolume(
            series=series,
            volume=volume,
            story_profile=series,
            source_profile="pdf-llm-ocr",
            text_units=text_units,
        ),
    )


def _default_units() -> tuple[PreparedTextUnit, ...]:
    return (
        _unit(0, "Prologue\nA quiet start."),
        _unit(1, "Chapter 2\nThe main body."),
        _unit(2, "Epilogue\nA quiet end."),
    )


def _unit(index: int, text: str, *, needs_review: bool = False) -> PreparedTextUnit:
    return PreparedTextUnit(
        text_unit_id=f"unit_{index:06d}",
        order=index,
        text=text,
        source_path=f"source/pages/{index + 1:03d}.txt",
        source_locator={"page": index + 1},
        needs_review=needs_review,
    )
