"""End-to-end integration tests for the prepare-stage runner with fake seams."""

from __future__ import annotations

import shutil
from pathlib import Path

import fitz
import pytest
from automations.ln_voice_over_v2.common import paths
from automations.ln_voice_over_v2.stages.prepare.contracts import PreparedVolume
from automations.ln_voice_over_v2.stages.prepare.ocr import OcrPageResult
from automations.ln_voice_over_v2.stages.prepare.runner import (
    SOURCE_PROFILE,
    PrepareConfig,
    PrepareResult,
    run_prepare,
)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a tiny two-page PDF fixture with PyMuPDF."""
    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    for page_number in range(1, 3):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {page_number}")
    document.save(pdf_path)
    document.close()
    return pdf_path


def test_run_prepare_writes_round_trippable_prepared_volume(
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    """The runner assembles and persists a complete prepared volume."""
    result = _run_with_fixture(tmp_path, sample_pdf, volume="v1")
    prepared = result.prepared_volume
    volume_root = paths.volume_root(tmp_path, prepared.series, prepared.volume)
    round_tripped = PreparedVolume.model_validate_json(
        result.prepared_volume_path.read_text(encoding="utf-8")
    )

    assert result.prepared_volume_path.is_file()
    assert round_tripped == prepared
    assert prepared.source_profile == SOURCE_PROFILE
    assert prepared.story_profile == prepared.series
    assert len(prepared.text_units) == 2
    assert [unit.needs_review for unit in prepared.text_units] == [False] * len(
        prepared.text_units
    )
    assert result.page_count == len(prepared.text_units)
    assert len(prepared.media) == 1
    assert result.illustration_count == 1
    for unit in prepared.text_units:
        assert (volume_root / unit.source_path).is_file()
    for media in prepared.media:
        assert (volume_root / media.path).is_file()
        assert (volume_root / media.source_path).is_file()


def test_run_prepare_uses_explicit_story_profile(
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    """An explicit story profile overrides the default series profile."""
    result = _run_with_fixture(
        tmp_path,
        sample_pdf,
        volume="v2",
        story_profile="explicit-profile",
    )

    assert result.prepared_volume.story_profile == "explicit-profile"


def _run_with_fixture(
    tmp_path: Path,
    sample_pdf: Path,
    *,
    volume: str,
    story_profile: str | None = None,
) -> PrepareResult:
    config = PrepareConfig(
        anyflip_url="https://anyflip.example/book",
        series="series-one",
        volume=volume,
        data_root=tmp_path,
        story_profile=story_profile,
        workers=1,
    )

    def fake_download_fn(_url: str, dest_pdf: Path) -> Path:
        dest_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sample_pdf, dest_pdf)
        return dest_pdf

    def fake_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        if page == 2:
            return OcrPageResult(transcript="", is_illustration=True)
        return OcrPageResult(transcript=f"Prose from page {page}", is_illustration=False)

    return run_prepare(config, download_fn=fake_download_fn, ocr_fn=fake_ocr_fn)
