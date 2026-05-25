"""Tests for prepare-stage text-unit composition."""

from __future__ import annotations

from pathlib import Path

import pytest
from automations.ln_voice_over_v2.stages.prepare.ocr import OcrPageResult
from automations.ln_voice_over_v2.stages.prepare.rasterizer import RasterizedPage
from automations.ln_voice_over_v2.stages.prepare.text_units import build_text_units


def test_build_text_units_emits_contiguous_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every page becomes a contiguous zero-indexed text unit."""
    monkeypatch.chdir(tmp_path)
    ocr_results = [
        OcrPageResult(transcript="Opening text", is_illustration=False),
        OcrPageResult(transcript="", is_illustration=True),
        OcrPageResult(transcript="Closing text", is_illustration=False),
    ]
    rasterized = _rasterized_pages(tmp_path, 3)

    text_units = build_text_units(ocr_results, rasterized)

    assert [unit.order for unit in text_units] == [0, 1, 2]
    assert [unit.text_unit_id for unit in text_units] == [
        "unit_000000",
        "unit_000001",
        "unit_000002",
    ]
    assert [unit.text for unit in text_units] == [
        "Opening text",
        "",
        "Closing text",
    ]
    for unit, page in zip(text_units, [1, 2, 3], strict=True):
        assert unit.source_locator["page"] == page
        assert unit.source_path == f"source/pages/{page:03d}.png"
        assert int(unit.text_unit_id.removeprefix("unit_")) == unit.order


def test_build_text_units_rejects_mismatched_counts(tmp_path: Path) -> None:
    """OCR results and rasterized pages must align one-to-one."""
    ocr_results = [OcrPageResult(transcript="Only one OCR result", is_illustration=False)]
    rasterized = _rasterized_pages(tmp_path, 2)

    with pytest.raises(AssertionError):
        build_text_units(ocr_results, rasterized)


def test_build_text_units_rejects_non_contiguous_page_order(tmp_path: Path) -> None:
    """Rasterized pages must be sorted in contiguous 1-indexed order."""
    ocr_results = [
        OcrPageResult(transcript="Page one", is_illustration=False),
        OcrPageResult(transcript="Page three", is_illustration=False),
    ]
    rasterized = [
        RasterizedPage(page=1, path=tmp_path / "001.png"),
        RasterizedPage(page=3, path=tmp_path / "003.png"),
    ]

    with pytest.raises(AssertionError):
        build_text_units(ocr_results, rasterized)


def _rasterized_pages(tmp_path: Path, count: int) -> list[RasterizedPage]:
    return [
        RasterizedPage(page=page, path=tmp_path / f"{page:03d}.png")
        for page in range(1, count + 1)
    ]
