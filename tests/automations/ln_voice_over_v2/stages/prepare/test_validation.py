"""Tests for prepared volume filesystem validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from automations.ln_voice_over_v2.common.enums import MediaType
from automations.ln_voice_over_v2.common.errors import ContractValidationError
from automations.ln_voice_over_v2.stages.prepare.contracts import (
    PreparedMedia,
    PreparedTextUnit,
    PreparedVolume,
)
from automations.ln_voice_over_v2.stages.prepare.validation import validate_prepared_volume


def test_validate_prepared_volume_accepts_consistent_files(tmp_path: Path) -> None:
    """A prepared volume passes when every embedded path resolves under volume_root."""
    volume = _prepared_volume()
    _write_required_files(tmp_path)

    validate_prepared_volume(volume, tmp_path)


def test_validate_prepared_volume_reports_empty_text_units(tmp_path: Path) -> None:
    """Prepared volumes must contain at least one text unit."""
    volume = _prepared_volume(text_units=())
    _write_required_files(tmp_path)

    with pytest.raises(ContractValidationError) as exc_info:
        validate_prepared_volume(volume, tmp_path)

    assert _codes(exc_info.value) == {"text_units_empty"}


def test_validate_prepared_volume_reports_text_unit_order_gap(tmp_path: Path) -> None:
    """Text unit orders must be contiguous from 0."""
    volume = _prepared_volume(
        text_units=(
            _text_unit("unit_000000", 0, "source/pages/001.png"),
            _text_unit("unit_000002", 2, "source/pages/002.png"),
        )
    )
    _write_required_files(tmp_path)

    with pytest.raises(ContractValidationError) as exc_info:
        validate_prepared_volume(volume, tmp_path)

    assert "text_unit_order_gap" in _codes(exc_info.value)


def test_validate_prepared_volume_reports_text_unit_order_duplicate(tmp_path: Path) -> None:
    """Duplicate text unit orders are reported."""
    volume = _prepared_volume(
        text_units=(
            _text_unit("unit_000000", 0, "source/pages/001.png"),
            _text_unit("unit_000001", 0, "source/pages/002.png"),
        )
    )
    _write_required_files(tmp_path)

    with pytest.raises(ContractValidationError) as exc_info:
        validate_prepared_volume(volume, tmp_path)

    assert "text_unit_order_duplicate" in _codes(exc_info.value)


def test_validate_prepared_volume_reports_missing_text_unit_source(tmp_path: Path) -> None:
    """Missing text-unit source files are reported."""
    volume = _prepared_volume()
    _write_required_files(tmp_path)
    (tmp_path / "source/pages/001.png").unlink()

    with pytest.raises(ContractValidationError) as exc_info:
        validate_prepared_volume(volume, tmp_path)

    assert "text_unit_source_missing" in _codes(exc_info.value)


def test_validate_prepared_volume_reports_missing_media_paths(tmp_path: Path) -> None:
    """Missing prepared-media and source-media files use distinct codes."""
    volume = _prepared_volume()
    _write_required_files(tmp_path)
    (tmp_path / "prepared/media/illustration-001.png").unlink()
    (tmp_path / "source/pages/002.png").unlink()

    with pytest.raises(ContractValidationError) as exc_info:
        validate_prepared_volume(volume, tmp_path)

    assert _codes(exc_info.value) >= {"media_path_missing", "media_source_missing"}


def test_validate_prepared_volume_reports_media_order_gap(tmp_path: Path) -> None:
    """Media orders must be contiguous from 0."""
    volume = _prepared_volume(
        media=(
            _media("illustration-001", 0, "prepared/media/illustration-001.png"),
            _media("illustration-002", 2, "prepared/media/illustration-002.png"),
        )
    )
    _write_required_files(tmp_path, media_paths=("illustration-001.png", "illustration-002.png"))

    with pytest.raises(ContractValidationError) as exc_info:
        validate_prepared_volume(volume, tmp_path)

    assert "media_order_gap" in _codes(exc_info.value)


def test_validate_prepared_volume_reports_media_order_duplicate(tmp_path: Path) -> None:
    """Duplicate media orders are reported."""
    volume = _prepared_volume(
        media=(
            _media("illustration-001", 0, "prepared/media/illustration-001.png"),
            _media("illustration-002", 0, "prepared/media/illustration-002.png"),
        )
    )
    _write_required_files(tmp_path, media_paths=("illustration-001.png", "illustration-002.png"))

    with pytest.raises(ContractValidationError) as exc_info:
        validate_prepared_volume(volume, tmp_path)

    assert "media_order_duplicate" in _codes(exc_info.value)


def _prepared_volume(
    *,
    text_units: tuple[PreparedTextUnit, ...] | None = None,
    media: tuple[PreparedMedia, ...] | None = None,
) -> PreparedVolume:
    return PreparedVolume(
        series="series-one",
        volume="v1",
        story_profile="series-one",
        source_profile="pdf-llm-ocr",
        text_units=text_units
        if text_units is not None
        else (_text_unit("unit_000000", 0, "source/pages/001.png"),),
        media=media
        if media is not None
        else (
            PreparedMedia(
                media_id="illustration-001",
                order=0,
                media_type=MediaType.ILLUSTRATION,
                path="prepared/media/illustration-001.png",
                source_path="source/pages/002.png",
            ),
        ),
    )


def _text_unit(text_unit_id: str, order: int, source_path: str) -> PreparedTextUnit:
    return PreparedTextUnit(
        text_unit_id=text_unit_id,
        order=order,
        text="Text",
        source_path=source_path,
        source_locator={"page": order + 1},
    )


def _media(media_id: str, order: int, path: str) -> PreparedMedia:
    return PreparedMedia(
        media_id=media_id,
        order=order,
        media_type=MediaType.ILLUSTRATION,
        path=path,
        source_path="source/pages/002.png",
    )


def _write_required_files(
    volume_root: Path, *, media_paths: tuple[str, ...] = ("illustration-001.png",)
) -> None:
    for path in (
        volume_root / "source/pages/001.png",
        volume_root / "source/pages/002.png",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")

    media_dir = volume_root / "prepared/media"
    media_dir.mkdir(parents=True, exist_ok=True)
    for filename in media_paths:
        (media_dir / filename).write_bytes(b"png")


def _codes(error: ContractValidationError) -> set[str]:
    return {problem.code for problem in error.problems}
