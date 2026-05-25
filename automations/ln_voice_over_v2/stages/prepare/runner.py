"""Prepare-stage orchestration for one AnyFlip-backed volume."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final

from ...common import paths
from ...common.ids import ProfileId, SeriesId, VolumeId
from ...common.json_io import save_json_contract
from .contracts import PreparedVolume
from .downloader import download_anyflip
from .media import collect_media
from .ocr import OcrPageResult, load_cached_ocr, run_codex_ocr, save_ocr
from .prompts import OCR_PROMPT
from .rasterizer import RasterizedPage, rasterize_pdf
from .text_units import build_text_units
from .validation import validate_prepared_volume

logger = logging.getLogger("ln_voice_over_v2.prepare")

SOURCE_PROFILE: Final[str] = "pdf-llm-ocr"


@dataclass(frozen=True)
class PrepareConfig:
    """Configuration for a prepare-stage run."""

    anyflip_url: str
    series: SeriesId
    volume: VolumeId
    data_root: Path = paths.DEFAULT_PROJECT_DATA_ROOT
    story_profile: ProfileId | None = None
    ocr_model: str = "gpt-5.5"
    workers: int = 4
    force: bool = False
    force_ocr: bool = False


@dataclass(frozen=True)
class PrepareResult:
    """Result metadata from a completed prepare-stage run."""

    prepared_volume_path: Path
    prepared_volume: PreparedVolume
    page_count: int
    illustration_count: int


def run_prepare(
    config: PrepareConfig,
    *,
    download_fn: Callable[[str, Path], None] | None = None,
    ocr_fn: Callable[[Path], OcrPageResult] | None = None,
) -> PrepareResult:
    """Run the prepare stage for one volume.

    Args:
        config: Prepare-stage configuration.
        download_fn: Optional downloader seam for tests.
        ocr_fn: Optional OCR seam for tests.

    Returns:
        Prepared volume metadata and counts.
    """
    volume_root = paths.volume_root(config.data_root, config.series, config.volume)
    prepared_volume_path = paths.prepared_volume_path(
        config.data_root, config.series, config.volume
    )
    source_pdf = volume_root / "source" / "volume.pdf"
    pages_dir = volume_root / "source" / "pages"
    ocr_dir = volume_root / "source" / "ocr"

    if config.force:
        shutil.rmtree(ocr_dir, ignore_errors=True)
        shutil.rmtree(volume_root / "prepared", ignore_errors=True)

    ocr_dir.mkdir(parents=True, exist_ok=True)

    if download_fn is None:
        download_fn = partial(
            download_anyflip,
            executable="anyflip-downloader",
            timeout_seconds=600,
        )
    if ocr_fn is None:
        ocr_fn = partial(
            run_codex_ocr,
            model=config.ocr_model,
            executable="codex",
            timeout_seconds=180,
            prompt=OCR_PROMPT,
        )

    logger.info("downloading source PDF to %s", source_pdf)
    download_fn(config.anyflip_url, source_pdf)

    rasterized = sorted(
        rasterize_pdf(source_pdf, pages_dir, dpi=200, force=config.force),
        key=lambda page: page.page,
    )
    ocr_results = _ocr_all_pages(
        rasterized,
        ocr_dir,
        ocr_fn,
        workers=config.workers,
        use_cache=not (config.force or config.force_ocr),
    )

    prepared = PreparedVolume(
        series=config.series,
        volume=config.volume,
        story_profile=config.story_profile if config.story_profile is not None else config.series,
        source_profile=SOURCE_PROFILE,
        text_units=build_text_units(ocr_results, rasterized),
        media=collect_media(
            ocr_results,
            rasterized,
            volume_root,
            rebuild=config.force or config.force_ocr,
        ),
    )
    validate_prepared_volume(prepared, volume_root)
    save_json_contract(prepared_volume_path, prepared)

    return PrepareResult(
        prepared_volume_path=prepared_volume_path,
        prepared_volume=prepared,
        page_count=len(prepared.text_units),
        illustration_count=len(prepared.media),
    )


def _ocr_all_pages(
    rasterized: list[RasterizedPage],
    ocr_dir: Path,
    ocr_fn: Callable[[Path], OcrPageResult],
    *,
    workers: int,
    use_cache: bool,
) -> list[OcrPageResult]:
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_ocr_one_page, page, ocr_dir, ocr_fn, use_cache=use_cache)
            for page in rasterized
        ]
        page_results = [future.result() for future in futures]

    return [
        result for _page, result in sorted(page_results, key=lambda page_result: page_result[0])
    ]


def _ocr_one_page(
    rasterized_page: RasterizedPage,
    ocr_dir: Path,
    ocr_fn: Callable[[Path], OcrPageResult],
    *,
    use_cache: bool,
) -> tuple[int, OcrPageResult]:
    page = rasterized_page.page
    cache_path = ocr_dir / f"{page:03d}.json"

    if use_cache and cache_path.exists():
        cached = load_cached_ocr(cache_path)
        if cached is not None:
            logger.info("reusing cached OCR for page %03d", page)
            return page, cached
        logger.warning("source/ocr/%03d.json failed strict parse; recomputing", page)

    logger.info("running OCR for page %03d", page)
    result = ocr_fn(rasterized_page.path)
    save_ocr(cache_path, result)
    return page, result
