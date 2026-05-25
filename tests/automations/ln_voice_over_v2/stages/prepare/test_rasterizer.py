"""Tests for prepare-stage PDF rasterization."""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest
from automations.ln_voice_over_v2.stages.prepare.rasterizer import rasterize_pdf
from PIL import Image


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


def test_rasterize_pdf_renders_one_indexed_rgb_pngs(sample_pdf: Path, tmp_path: Path) -> None:
    """PDF pages render to sorted, 1-indexed RGB PNGs."""
    pages_dir = tmp_path / "pages"

    pages = rasterize_pdf(sample_pdf, pages_dir)

    assert [page.page for page in pages] == [1, 2]
    assert [page.path.name for page in pages] == ["001.png", "002.png"]
    assert sorted(path.name for path in pages_dir.iterdir()) == ["001.png", "002.png"]
    assert Image.open(pages[0].path).mode == "RGB"
    assert Image.open(pages[1].path).mode == "RGB"


def test_rasterize_pdf_skips_existing_pngs(sample_pdf: Path, tmp_path: Path) -> None:
    """A second run preserves mtimes for already-rendered page PNGs."""
    pages_dir = tmp_path / "pages"
    rasterize_pdf(sample_pdf, pages_dir)
    page_path = pages_dir / "001.png"
    fixed_mtime_ns = 1_700_000_000_000_000_000
    os.utime(page_path, ns=(fixed_mtime_ns, fixed_mtime_ns))

    rasterize_pdf(sample_pdf, pages_dir)

    assert page_path.stat().st_mtime_ns == fixed_mtime_ns


def test_rasterize_pdf_force_rewrites_existing_pngs(sample_pdf: Path, tmp_path: Path) -> None:
    """force=True rewrites already-rendered page PNGs (mtime changes)."""
    pages_dir = tmp_path / "pages"
    rasterize_pdf(sample_pdf, pages_dir)
    page_path = pages_dir / "001.png"
    fixed_mtime_ns = 1_700_000_000_000_000_000
    os.utime(page_path, ns=(fixed_mtime_ns, fixed_mtime_ns))

    rasterize_pdf(sample_pdf, pages_dir, force=True)

    assert page_path.stat().st_mtime_ns != fixed_mtime_ns


def test_rasterize_pdf_rejects_empty_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An openable but zero-page PDF aborts before OCR work can start."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    class _ZeroPageDoc:
        page_count = 0

        def __enter__(self) -> _ZeroPageDoc:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(
        "automations.ln_voice_over_v2.stages.prepare.rasterizer.fitz.open",
        lambda *_a, **_kw: _ZeroPageDoc(),
    )

    with pytest.raises(RuntimeError, match="zero pages"):
        rasterize_pdf(pdf_path, tmp_path / "pages")
