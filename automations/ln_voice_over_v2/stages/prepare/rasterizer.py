"""PDF rasterization helpers for the LNVO v2 prepare stage."""

from __future__ import annotations

from pathlib import Path

import fitz
from pydantic import BaseModel, ConfigDict, Field


class RasterizedPage(BaseModel):
    """Rasterized page image metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int = Field(ge=1)
    path: Path


def rasterize_pdf(
    pdf_path: Path,
    pages_dir: Path,
    *,
    dpi: int = 200,
    force: bool = False,
) -> list[RasterizedPage]:
    """Render every page of a PDF to 1-indexed PNG files.

    Args:
        pdf_path: Source PDF path.
        pages_dir: Destination directory for page PNGs.
        dpi: Render DPI.
        force: When True, rewrite every page PNG even if it already exists on disk.

    Returns:
        One rasterized page entry per PDF page, sorted by page number.

    Raises:
        RuntimeError: If the PDF has zero pages.
    """
    pages_dir.mkdir(parents=True, exist_ok=True)
    rasterized: list[RasterizedPage] = []
    scale = dpi / 72

    with fitz.open(pdf_path) as document:
        if document.page_count < 1:
            raise RuntimeError(f"PDF at {pdf_path} has zero pages")

        for page_index in range(document.page_count):
            page_number = page_index + 1
            image_path = pages_dir / f"{page_number:03d}.png"
            if force or not image_path.exists():
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pixmap.save(str(image_path))
            rasterized.append(RasterizedPage(page=page_number, path=image_path))

    return rasterized
