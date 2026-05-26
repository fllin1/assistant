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
from .ocr import (
    OcrPageResult,
    _is_failed_ocr,
    load_cached_ocr,
    run_codex_ocr,
    save_ocr,
)
from .prompts import OCR_PROMPTS
from .rasterizer import RasterizedPage, rasterize_pdf
from .text_units import build_text_units
from .validation import validate_prepared_volume

logger = logging.getLogger("ln_voice_over_v2.prepare")

SOURCE_PROFILE: Final[str] = "pdf-llm-ocr"
_OCR_MAX_ATTEMPTS: Final[int] = 3


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


@dataclass(frozen=True)
class _OcrPageOutcome:
    """Runner-internal OCR result plus review routing metadata for one page."""

    page: int
    result: OcrPageResult
    needs_review: bool


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

    logger.info("downloading source PDF to %s", source_pdf)
    download_fn(config.anyflip_url, source_pdf)

    rasterized = sorted(
        rasterize_pdf(source_pdf, pages_dir, dpi=200, force=config.force),
        key=lambda page: page.page,
    )
    outcomes = _ocr_all_pages(
        rasterized,
        ocr_dir,
        ocr_fn,
        config,
        workers=config.workers,
        use_cache=not (config.force or config.force_ocr),
    )
    ocr_results = [outcome.result for outcome in outcomes]
    needs_review = tuple(outcome.needs_review for outcome in outcomes)

    prepared = PreparedVolume(
        series=config.series,
        volume=config.volume,
        story_profile=config.story_profile if config.story_profile is not None else config.series,
        source_profile=SOURCE_PROFILE,
        text_units=build_text_units(ocr_results, rasterized, needs_review),
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
    ocr_fn: Callable[[Path], OcrPageResult] | None,
    config: PrepareConfig,
    *,
    workers: int,
    use_cache: bool,
) -> list[_OcrPageOutcome]:
    """Run OCR for all pages and summarize which pages need manual review.

    Args:
        rasterized: Rasterized page metadata in page order.
        ocr_dir: Directory containing per-page OCR cache files.
        ocr_fn: Optional test seam. When absent, the worker builds Codex OCR
            callables from the configured prompt escalation list.
        config: Prepare-stage configuration.
        workers: Maximum OCR worker threads.
        use_cache: Whether valid non-failure cache entries may be reused.

    Returns:
        One OCR outcome per page, sorted by ascending 1-indexed page number.
    """
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _ocr_one_page,
                page,
                ocr_dir,
                ocr_fn,
                config,
                use_cache=use_cache,
            )
            for page in rasterized
        ]
        outcomes: list[_OcrPageOutcome] = []
        for future in futures:
            outcomes.append(future.result())

    outcomes.sort(key=lambda outcome: outcome.page)
    review_pages = [outcome.page for outcome in outcomes if outcome.needs_review]
    ok_count = len(outcomes) - len(review_pages)
    total = len(outcomes)
    if review_pages:
        logger.warning("prepare: %d page(s) need review: %s", len(review_pages), review_pages)
    logger.info("prepare: %d/%d pages OK, %d needs_review", ok_count, total, len(review_pages))
    return outcomes


def _ocr_one_page(
    rasterized_page: RasterizedPage,
    ocr_dir: Path,
    ocr_fn: Callable[[Path], OcrPageResult] | None,
    config: PrepareConfig,
    *,
    use_cache: bool,
) -> _OcrPageOutcome:
    """OCR one page with cache reuse, semantic retry, and sentinel emission.

    Args:
        rasterized_page: Rasterized page image to OCR.
        ocr_dir: Directory containing per-page OCR cache files.
        ocr_fn: Optional injected OCR callable. When absent, each attempt uses
            the corresponding prompt variant from `OCR_PROMPTS`.
        config: Prepare-stage configuration used by the default OCR callable.
        use_cache: Whether valid non-failure cache entries may be reused.

    Returns:
        The page OCR result and whether the exhausted retry budget requires
        downstream review.
    """
    page = rasterized_page.page
    cache_path = ocr_dir / f"{page:03d}.json"

    if use_cache and cache_path.exists():
        cached = load_cached_ocr(cache_path)
        if cached is not None:
            if _is_failed_ocr(cached):
                logger.warning(
                    "source/ocr/%03d.json contains a refusal-style transcript; recomputing",
                    page,
                )
            else:
                logger.info("reusing cached OCR for page %03d", page)
                return _OcrPageOutcome(page=page, result=cached, needs_review=False)
        else:
            logger.warning("source/ocr/%03d.json failed strict parse; recomputing", page)

    for attempt_index in range(_OCR_MAX_ATTEMPTS):
        per_attempt_ocr_fn = (
            ocr_fn if ocr_fn is not None else _make_default_ocr_fn(config, attempt_index)
        )
        logger.info("running OCR for page %03d", page)
        result = per_attempt_ocr_fn(rasterized_page.path)
        if not _is_failed_ocr(result):
            save_ocr(cache_path, result)
            return _OcrPageOutcome(page=page, result=result, needs_review=False)
        if attempt_index < _OCR_MAX_ATTEMPTS - 1:
            continue

        sentinel = OcrPageResult(transcript="", is_illustration=False)
        save_ocr(cache_path, sentinel)
        return _OcrPageOutcome(page=page, result=sentinel, needs_review=True)

    raise AssertionError("unreachable OCR retry loop exit")


def _make_default_ocr_fn(
    config: PrepareConfig, prompt_index: int
) -> Callable[[Path], OcrPageResult]:
    """Build the runtime OCR boundary for one prompt escalation attempt.

    Args:
        config: Prepare-stage configuration.
        prompt_index: Zero-based index into `OCR_PROMPTS`.

    Returns:
        A single-page OCR callable using the selected prompt.
    """
    return partial(
        run_codex_ocr,
        model=config.ocr_model,
        executable="codex",
        timeout_seconds=180,
        prompt=OCR_PROMPTS[prompt_index],
    )
