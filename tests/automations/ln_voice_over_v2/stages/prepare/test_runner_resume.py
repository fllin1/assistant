"""Integration tests for prepare-stage resume and force behavior."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import fitz
import pytest
from automations.ln_voice_over_v2.common import paths
from automations.ln_voice_over_v2.stages.prepare import __main__ as prepare_main
from automations.ln_voice_over_v2.stages.prepare import runner
from automations.ln_voice_over_v2.stages.prepare.ocr import (
    OcrPageResult,
    load_cached_ocr,
    save_ocr,
)
from automations.ln_voice_over_v2.stages.prepare.rasterizer import (
    RasterizedPage,
    rasterize_pdf,
)
from automations.ln_voice_over_v2.stages.prepare.runner import PrepareConfig, run_prepare

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


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


def test_reuses_valid_cache_and_recomputes_invalid_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Valid OCR cache entries are reused while malformed entries are recomputed."""
    config = _config(tmp_path)
    volume_root = paths.volume_root(tmp_path, config.series, config.volume)
    ocr_dir = volume_root / "source" / "ocr"
    ocr_dir.mkdir(parents=True)
    save_ocr(ocr_dir / "001.json", OcrPageResult(transcript="cached", is_illustration=False))
    (ocr_dir / "002.json").write_text('{"transcript":"missing bool"}', encoding="utf-8")
    _patch_fake_rasterizer(monkeypatch)
    ocr_calls: list[int] = []

    def fake_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        ocr_calls.append(page)
        return OcrPageResult(transcript=f"fresh {page}", is_illustration=False)

    caplog.set_level("WARNING", logger="ln_voice_over_v2.prepare")
    result = run_prepare(config, download_fn=_fake_download, ocr_fn=fake_ocr_fn)

    warnings = [
        record.getMessage()
        for record in caplog.records
        if (
            record.levelname == "WARNING"
            and "failed strict parse; recomputing" in record.getMessage()
        )
    ]
    assert ocr_calls == [2]
    assert warnings == ["source/ocr/002.json failed strict parse; recomputing"]
    assert result.page_count == 2


def test_force_recomputes_ocr_rerasterizes_and_rebuilds_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """force=True skips cache, rewrites page images, and clears stale media."""
    config = _config(tmp_path, force=True)
    volume_root = paths.volume_root(tmp_path, config.series, config.volume)
    _write_cached_ocr(volume_root, count=2)
    leftover = volume_root / "prepared" / "media" / "illustration-013.png"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(PNG_BYTES + b"stale")
    writes: list[int] = []
    force_flags: list[bool] = []
    _patch_fake_rasterizer(monkeypatch, writes=writes, force_flags=force_flags)
    ocr_calls: list[int] = []

    def fake_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        ocr_calls.append(page)
        return OcrPageResult(transcript=f"fresh {page}", is_illustration=page == 2)

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=fake_ocr_fn)

    assert force_flags == [True]
    assert writes == [1, 2]
    assert ocr_calls == [1, 2]
    assert not leftover.exists()
    assert (volume_root / "prepared" / "media" / "illustration-001.png").is_file()
    assert result.illustration_count == 1


def test_force_ocr_recomputes_ocr_reuses_rasters_and_rebuilds_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """force_ocr=True skips cache without rewriting existing page images."""
    config = _config(tmp_path, force_ocr=True)
    volume_root = paths.volume_root(tmp_path, config.series, config.volume)
    _write_page_pngs(volume_root, count=2)
    _write_cached_ocr(volume_root, count=2)
    leftover = volume_root / "prepared" / "media" / "illustration-013.png"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(PNG_BYTES + b"stale")
    writes: list[int] = []
    force_flags: list[bool] = []
    _patch_fake_rasterizer(monkeypatch, writes=writes, force_flags=force_flags)
    ocr_calls: list[int] = []

    def fake_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        ocr_calls.append(page)
        return OcrPageResult(transcript=f"fresh {page}", is_illustration=page == 1)

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=fake_ocr_fn)

    assert force_flags == [False]
    assert writes == []
    assert ocr_calls == [1, 2]
    assert not leftover.exists()
    assert (volume_root / "prepared" / "media" / "illustration-001.png").is_file()
    assert result.illustration_count == 1


def test_cli_rejects_force_and_force_ocr_without_calling_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI rejects mutually exclusive force flags before invoking the runner."""
    called = False

    def fake_run_prepare(_config: PrepareConfig) -> object:
        nonlocal called
        called = True
        raise AssertionError("runner should not be called")

    monkeypatch.setattr(prepare_main, "run_prepare", fake_run_prepare)

    exit_code = prepare_main.main(
        [
            "--url",
            "https://anyflip.example/book",
            "--series",
            "s",
            "--volume",
            "v",
            "--force",
            "--force-ocr",
        ]
    )

    assert exit_code != 0
    assert not called


def test_partial_progress_survives_failed_ocr_and_second_run_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later page failure leaves earlier saved OCR cache usable for resume."""
    config = _config(tmp_path, workers=2)
    volume_root = paths.volume_root(tmp_path, config.series, config.volume)
    _patch_fake_rasterizer(monkeypatch)
    first_calls: list[int] = []

    def failing_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        first_calls.append(page)
        if page == 2:
            raise RuntimeError("page 2 failed")
        return OcrPageResult(transcript="page 1", is_illustration=False)

    with pytest.raises(RuntimeError, match="page 2 failed"):
        run_prepare(config, download_fn=_fake_download, ocr_fn=failing_ocr_fn)

    assert sorted(first_calls) == [1, 2]
    assert load_cached_ocr(volume_root / "source" / "ocr" / "001.json") == OcrPageResult(
        transcript="page 1",
        is_illustration=False,
    )
    assert not (volume_root / "source" / "ocr" / "002.json").exists()

    second_calls: list[int] = []

    def resume_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        second_calls.append(page)
        return OcrPageResult(transcript=f"page {page}", is_illustration=False)

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=resume_ocr_fn)

    assert second_calls == [2]
    assert result.page_count == 2


def test_rasterize_without_ocr_resume_preserves_existing_page_pngs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_pdf: Path,
) -> None:
    """Existing rasters are reused while missing OCR cache entries are filled."""
    config = _config(tmp_path)
    volume_root = paths.volume_root(tmp_path, config.series, config.volume)
    source_pdf = volume_root / "source" / "volume.pdf"
    source_pdf.parent.mkdir(parents=True)
    shutil.copyfile(sample_pdf, source_pdf)
    pages_dir = volume_root / "source" / "pages"
    rasterize_pdf(source_pdf, pages_dir)
    fixed_mtime_ns = 1_700_000_000_000_000_000
    for page_png in pages_dir.glob("*.png"):
        os.utime(page_png, ns=(fixed_mtime_ns, fixed_mtime_ns))
    before_mtimes = {
        page_png.name: page_png.stat().st_mtime_ns for page_png in pages_dir.glob("*.png")
    }
    rasterize_calls: list[bool] = []
    real_rasterize_pdf = runner.rasterize_pdf

    def tracked_rasterize_pdf(
        pdf_path: Path,
        target_pages_dir: Path,
        *,
        dpi: int = 200,
        force: bool = False,
    ) -> list[RasterizedPage]:
        rasterize_calls.append(force)
        return real_rasterize_pdf(pdf_path, target_pages_dir, dpi=dpi, force=force)

    monkeypatch.setattr(runner, "rasterize_pdf", tracked_rasterize_pdf)
    ocr_calls: list[int] = []

    def fake_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        ocr_calls.append(page)
        return OcrPageResult(transcript=f"page {page}", is_illustration=False)

    result = run_prepare(
        config,
        download_fn=lambda _url, dest_pdf: shutil.copyfile(sample_pdf, dest_pdf),
        ocr_fn=fake_ocr_fn,
    )

    after_mtimes = {
        page_png.name: page_png.stat().st_mtime_ns for page_png in pages_dir.glob("*.png")
    }
    assert rasterize_calls == [False]
    assert before_mtimes == after_mtimes
    assert ocr_calls == [1, 2]
    assert len(result.prepared_volume.text_units) == 2


def _config(
    tmp_path: Path,
    *,
    force: bool = False,
    force_ocr: bool = False,
    workers: int = 1,
) -> PrepareConfig:
    return PrepareConfig(
        anyflip_url="https://anyflip.example/book",
        series="series-one",
        volume="v1",
        data_root=tmp_path,
        workers=workers,
        force=force,
        force_ocr=force_ocr,
    )


def _fake_download(_url: str, dest_pdf: Path) -> Path:
    dest_pdf.parent.mkdir(parents=True, exist_ok=True)
    dest_pdf.write_bytes(b"%PDF-1.7 fake")
    return dest_pdf


def _patch_fake_rasterizer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    count: int = 2,
    writes: list[int] | None = None,
    force_flags: list[bool] | None = None,
) -> None:
    def fake_rasterize_pdf(
        _pdf_path: Path,
        pages_dir: Path,
        *,
        dpi: int = 200,
        force: bool = False,
    ) -> list[RasterizedPage]:
        del dpi
        if force_flags is not None:
            force_flags.append(force)
        pages_dir.mkdir(parents=True, exist_ok=True)
        rasterized: list[RasterizedPage] = []
        for page in range(1, count + 1):
            page_path = pages_dir / f"{page:03d}.png"
            if force or not page_path.exists():
                page_path.write_bytes(PNG_BYTES + bytes([page]) * 16)
                if writes is not None:
                    writes.append(page)
            rasterized.append(RasterizedPage(page=page, path=page_path))
        return rasterized

    monkeypatch.setattr(runner, "rasterize_pdf", fake_rasterize_pdf)


def _write_page_pngs(volume_root: Path, *, count: int) -> None:
    pages_dir = volume_root / "source" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for page in range(1, count + 1):
        (pages_dir / f"{page:03d}.png").write_bytes(PNG_BYTES + bytes([page]) * 16)


def _write_cached_ocr(volume_root: Path, *, count: int) -> None:
    ocr_dir = volume_root / "source" / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    for page in range(1, count + 1):
        save_ocr(
            ocr_dir / f"{page:03d}.json",
            OcrPageResult(transcript=f"cached {page}", is_illustration=False),
        )
