"""Prepared media composition helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from ...common.enums import MediaType
from .contracts import PreparedMedia
from .ocr import OcrPageResult
from .rasterizer import RasterizedPage


def collect_media(
    ocr_results: list[OcrPageResult],
    rasterized: list[RasterizedPage],
    volume_root: Path,
    *,
    rebuild: bool = False,
) -> tuple[PreparedMedia, ...]:
    """Copy illustration pages into `prepared/media/` and return contract rows.

    When `rebuild=True`, delete every existing file under `prepared/media/`
    before copying the new set so stale illustration PNGs for pages no longer
    flagged as illustrations do not survive a recompute.

    Args:
        ocr_results: OCR result for each rasterized page, in page order.
        rasterized: Rasterized page metadata, in 1-indexed page order.
        volume_root: Volume root containing `source/` and `prepared/`.
        rebuild: Whether to clear existing prepared media files before copying.

    Returns:
        Prepared media entries ordered by illustration sequence.
    """
    _assert_page_alignment(ocr_results, rasterized)

    media_dir = volume_root / "prepared" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    if rebuild:
        for existing_file in media_dir.rglob("*"):
            if existing_file.is_file():
                existing_file.unlink()

    media: list[PreparedMedia] = []
    for ocr_result, rasterized_page in zip(ocr_results, rasterized, strict=True):
        if not ocr_result.is_illustration:
            continue

        seq = len(media) + 1
        filename = f"illustration-{seq:03d}.png"
        destination = media_dir / filename
        shutil.copyfile(rasterized_page.path, destination)
        media.append(
            PreparedMedia(
                media_id=f"illustration-{seq:03d}",
                order=seq - 1,
                media_type=MediaType.ILLUSTRATION,
                path=f"prepared/media/{filename}",
                source_path=f"source/pages/{rasterized_page.page:03d}.png",
            )
        )

    return tuple(media)


def _assert_page_alignment(
    ocr_results: list[OcrPageResult],
    rasterized: list[RasterizedPage],
) -> None:
    assert len(ocr_results) == len(rasterized)
    assert [page.page for page in rasterized] == list(range(1, len(rasterized) + 1))
