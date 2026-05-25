"""Prepared text-unit composition helpers."""

from __future__ import annotations

from .contracts import PreparedTextUnit
from .ocr import OcrPageResult
from .rasterizer import RasterizedPage


def build_text_units(
    ocr_results: list[OcrPageResult],
    rasterized: list[RasterizedPage],
) -> tuple[PreparedTextUnit, ...]:
    """Emit one `PreparedTextUnit` per page in 1-indexed page order.

    Page-index convention: filesystem page numbers and the `page` key in
    `source_locator` are 1-indexed; `order` and the integer suffix of
    `text_unit_id` are 0-indexed. Illustration-only pages still emit a unit
    with empty `text` so `order` stays contiguous.

    Args:
        ocr_results: OCR result for each rasterized page, in page order.
        rasterized: Rasterized page metadata, in 1-indexed page order.

    Returns:
        Prepared text units ordered by page.
    """
    _assert_page_alignment(ocr_results, rasterized)

    return tuple(
        PreparedTextUnit(
            text_unit_id=f"unit_{rasterized_page.page - 1:06d}",
            order=rasterized_page.page - 1,
            text=ocr_result.transcript,
            source_path=f"source/pages/{rasterized_page.page:03d}.png",
            source_locator={"page": rasterized_page.page},
        )
        for ocr_result, rasterized_page in zip(ocr_results, rasterized, strict=True)
    )


def _assert_page_alignment(
    ocr_results: list[OcrPageResult],
    rasterized: list[RasterizedPage],
) -> None:
    assert len(ocr_results) == len(rasterized)
    assert [page.page for page in rasterized] == list(range(1, len(rasterized) + 1))
