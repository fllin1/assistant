"""Retry and sentinel tests for the prepare-stage runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from automations.ln_voice_over_v2.common import paths
from automations.ln_voice_over_v2.stages.prepare import runner
from automations.ln_voice_over_v2.stages.prepare.contracts import PreparedVolume
from automations.ln_voice_over_v2.stages.prepare.ocr import (
    OcrPageResult,
    load_cached_ocr,
    save_ocr,
)
from automations.ln_voice_over_v2.stages.prepare.rasterizer import RasterizedPage
from automations.ln_voice_over_v2.stages.prepare.runner import PrepareConfig, run_prepare

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_retry_success_on_attempt_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A refusal on attempt one is retried and replaced by the clean result."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    ocr_fn = Mock(
        side_effect=[
            OcrPageResult(transcript="Sorry, I can't provide that.", is_illustration=False),
            OcrPageResult(transcript="real body text", is_illustration=False),
        ]
    )

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    assert ocr_fn.call_count == 2
    assert result.prepared_volume.text_units[0].text == "real body text"
    assert result.prepared_volume.text_units[0].needs_review is False
    assert _cached_ocr(tmp_path) == OcrPageResult(
        transcript="real body text",
        is_illustration=False,
    )


def test_retry_success_on_attempt_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The runner allows two recoverable failures before accepting attempt three."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    ocr_fn = Mock(
        side_effect=[
            OcrPageResult(transcript="Sorry, I can't provide that.", is_illustration=False),
            OcrPageResult(transcript="", is_illustration=False),
            OcrPageResult(transcript="real body text", is_illustration=False),
        ]
    )

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    assert ocr_fn.call_count == 3
    assert result.prepared_volume.text_units[0].text == "real body text"
    assert result.prepared_volume.text_units[0].needs_review is False


def test_retry_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Three refusal transcripts produce a review sentinel and complete the run."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    ocr_fn = Mock(
        side_effect=[
            OcrPageResult(transcript="Sorry, I can't provide that.", is_illustration=False),
            OcrPageResult(transcript="Sorry, I can't provide that.", is_illustration=False),
            OcrPageResult(transcript="Sorry, I can't provide that.", is_illustration=False),
        ]
    )
    caplog.set_level("WARNING", logger="ln_voice_over_v2.prepare")

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    prepared_path = result.prepared_volume_path
    round_tripped = PreparedVolume.model_validate_json(prepared_path.read_text(encoding="utf-8"))
    warning_records = [
        record
        for record in caplog.records
        if record.levelname == "WARNING" and "need review" in record.getMessage()
    ]
    assert ocr_fn.call_count == 3
    assert result.prepared_volume.text_units[0].text == ""
    assert result.prepared_volume.text_units[0].needs_review is True
    assert prepared_path.exists()
    assert round_tripped == result.prepared_volume
    assert _cached_ocr(tmp_path) == OcrPageResult(transcript="", is_illustration=False)
    assert len(warning_records) == 1
    assert "1" in warning_records[0].getMessage()


def test_retry_exhausted_via_empty_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prompt-obeying sentinel shapes are retried and finally flagged for review."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    ocr_fn = Mock(
        side_effect=[
            OcrPageResult(transcript="", is_illustration=False),
            OcrPageResult(transcript="", is_illustration=False),
            OcrPageResult(transcript="", is_illustration=False),
        ]
    )

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    assert ocr_fn.call_count == 3
    assert result.prepared_volume.text_units[0].text == ""
    assert result.prepared_volume.text_units[0].needs_review is True
    assert _cached_ocr(tmp_path) == OcrPageResult(transcript="", is_illustration=False)


def test_retry_exhausted_via_mixed_failure_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refusal text and empty sentinels share the same retry budget."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    refusal = OcrPageResult(transcript="Sorry, I can't provide that.", is_illustration=False)
    sentinel = OcrPageResult(transcript="", is_illustration=False)
    ocr_fn = Mock(side_effect=[refusal, sentinel, refusal])

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    assert ocr_fn.call_count == 3
    assert result.prepared_volume.text_units[0].needs_review is True


def test_mixed_batch_partial_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A batch can complete with only the exhausted page flagged for review."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=3)
    page_attempts: dict[int, int] = {}

    def fake_ocr_fn(page_image: Path) -> OcrPageResult:
        page = int(page_image.stem)
        page_attempts[page] = page_attempts.get(page, 0) + 1
        if page == 1:
            return OcrPageResult(transcript="page 1 text", is_illustration=False)
        if page == 2 and page_attempts[page] == 1:
            return OcrPageResult(
                transcript="Sorry, I can't provide that.",
                is_illustration=False,
            )
        if page == 2:
            return OcrPageResult(transcript="page 2 text", is_illustration=False)
        return OcrPageResult(transcript="Sorry, I can't provide that.", is_illustration=False)

    caplog.set_level("INFO", logger="ln_voice_over_v2.prepare")

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=fake_ocr_fn)

    info_records = [
        record
        for record in caplog.records
        if (
            record.levelname == "INFO"
            and "prepare: 2/3 pages OK, 1 needs_review" in record.getMessage()
        )
    ]
    warning_records = [
        record
        for record in caplog.records
        if (
            record.levelname == "WARNING"
            and "need review" in record.getMessage()
            and "3" in record.getMessage()
        )
    ]
    assert len(result.prepared_volume.text_units) == 3
    assert [unit.needs_review for unit in result.prepared_volume.text_units] == [
        False,
        False,
        True,
    ]
    assert page_attempts == {1: 1, 2: 2, 3: 3}
    assert len(info_records) == 1
    assert len(warning_records) == 1


def test_cache_with_refusal_recomputes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A cached refusal transcript is treated as a cache miss and overwritten."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    _save_cached_ocr(
        tmp_path,
        OcrPageResult(
            transcript="Sorry, I can't provide a full verbatim transcription of this page.",
            is_illustration=False,
        ),
    )
    clean = OcrPageResult(transcript="clean transcript", is_illustration=False)
    ocr_fn = Mock(return_value=clean)
    caplog.set_level("WARNING", logger="ln_voice_over_v2.prepare")

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    warning_records = [
        record
        for record in caplog.records
        if record.levelname == "WARNING" and "refusal-style" in record.getMessage()
    ]
    assert len(warning_records) == 1
    assert "001" in warning_records[0].getMessage()
    assert ocr_fn.call_count == 1
    assert result.prepared_volume.text_units[0].text == clean.transcript
    assert result.prepared_volume.text_units[0].needs_review is False
    assert _cached_ocr(tmp_path) == clean


def test_cache_with_empty_sentinel_recomputes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stale exhausted-run sentinel is recomputed on the next resume run."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    _save_cached_ocr(tmp_path, OcrPageResult(transcript="", is_illustration=False))
    clean = OcrPageResult(transcript="clean transcript", is_illustration=False)
    ocr_fn = Mock(return_value=clean)
    caplog.set_level("WARNING", logger="ln_voice_over_v2.prepare")

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    warning_records = [
        record
        for record in caplog.records
        if record.levelname == "WARNING" and "refusal-style" in record.getMessage()
    ]
    assert len(warning_records) == 1
    assert "001" in warning_records[0].getMessage()
    assert ocr_fn.call_count == 1
    assert result.prepared_volume.text_units[0].text == clean.transcript
    assert result.prepared_volume.text_units[0].needs_review is False
    assert _cached_ocr(tmp_path) == clean


def test_cache_with_legit_illustration_keeps_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cached full-bleed illustration stays valid and does not call OCR."""
    config = _config(tmp_path)
    _patch_fake_rasterizer(monkeypatch, count=1)
    _save_cached_ocr(tmp_path, OcrPageResult(transcript="", is_illustration=True))
    ocr_fn = Mock(side_effect=RuntimeError("ocr_fn must NOT be called"))

    result = run_prepare(config, download_fn=_fake_download, ocr_fn=ocr_fn)

    assert ocr_fn.call_count == 0
    assert result.prepared_volume.text_units[0].text == ""
    assert result.prepared_volume.text_units[0].needs_review is False


def _config(tmp_path: Path) -> PrepareConfig:
    return PrepareConfig(
        anyflip_url="https://anyflip.example/book",
        series="series-one",
        volume="v1",
        data_root=tmp_path,
        workers=1,
    )


def _fake_download(_url: str, dest_pdf: Path) -> Path:
    dest_pdf.parent.mkdir(parents=True, exist_ok=True)
    dest_pdf.write_bytes(b"%PDF-1.7 fake")
    return dest_pdf


def _patch_fake_rasterizer(monkeypatch: pytest.MonkeyPatch, *, count: int) -> None:
    def fake_rasterize_pdf(
        _pdf_path: Path,
        pages_dir: Path,
        *,
        dpi: int = 200,
        force: bool = False,
    ) -> list[RasterizedPage]:
        del dpi
        pages_dir.mkdir(parents=True, exist_ok=True)
        rasterized: list[RasterizedPage] = []
        for page in range(1, count + 1):
            page_path = pages_dir / f"{page:03d}.png"
            if force or not page_path.exists():
                page_path.write_bytes(PNG_BYTES + bytes([page]) * 16)
            rasterized.append(RasterizedPage(page=page, path=page_path))
        return rasterized

    monkeypatch.setattr(runner, "rasterize_pdf", fake_rasterize_pdf)


def _save_cached_ocr(tmp_path: Path, result: OcrPageResult) -> None:
    save_ocr(_ocr_dir(tmp_path) / "001.json", result)


def _cached_ocr(tmp_path: Path) -> OcrPageResult | None:
    return load_cached_ocr(_ocr_dir(tmp_path) / "001.json")


def _ocr_dir(tmp_path: Path) -> Path:
    volume_root = paths.volume_root(tmp_path, "series-one", "v1")
    return volume_root / "source" / "ocr"
