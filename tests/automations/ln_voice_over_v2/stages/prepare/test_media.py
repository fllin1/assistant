"""Tests for prepare-stage media composition."""

from __future__ import annotations

from pathlib import Path

from automations.ln_voice_over_v2.common.enums import MediaType
from automations.ln_voice_over_v2.stages.prepare.media import collect_media
from automations.ln_voice_over_v2.stages.prepare.ocr import OcrPageResult
from automations.ln_voice_over_v2.stages.prepare.rasterizer import RasterizedPage

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_collect_media_copies_only_illustrations_with_contiguous_seq(tmp_path: Path) -> None:
    """Only illustration pages become prepared media entries."""
    rasterized = _write_rasterized_pages(tmp_path, 4)
    ocr_results = [
        OcrPageResult(transcript="Text page", is_illustration=False),
        OcrPageResult(transcript="", is_illustration=True),
        OcrPageResult(transcript="More text", is_illustration=False),
        OcrPageResult(transcript="", is_illustration=True),
    ]

    media = collect_media(ocr_results, rasterized, tmp_path)

    assert [entry.media_id for entry in media] == [
        "illustration-001",
        "illustration-002",
    ]
    assert [entry.order for entry in media] == [0, 1]
    assert [entry.media_type for entry in media] == [
        MediaType.ILLUSTRATION,
        MediaType.ILLUSTRATION,
    ]
    assert [entry.path for entry in media] == [
        "prepared/media/illustration-001.png",
        "prepared/media/illustration-002.png",
    ]
    assert [entry.source_path for entry in media] == [
        "source/pages/002.png",
        "source/pages/004.png",
    ]
    for seq, source_page in [(1, 2), (2, 4)]:
        copied = tmp_path / "prepared" / "media" / f"illustration-{seq:03d}.png"
        source = tmp_path / "source" / "pages" / f"{source_page:03d}.png"
        assert copied.read_bytes() == source.read_bytes()


def test_collect_media_rebuild_deletes_leftover_files(tmp_path: Path) -> None:
    """Rebuild mode removes stale prepared media files before copying."""
    media_dir = tmp_path / "prepared" / "media"
    media_dir.mkdir(parents=True)
    leftover = media_dir / "illustration-013.png"
    leftover.write_bytes(PNG_BYTES + b"leftover")
    rasterized = _write_rasterized_pages(tmp_path, 2)
    ocr_results = [
        OcrPageResult(transcript="", is_illustration=True),
        OcrPageResult(transcript="Text page", is_illustration=False),
    ]

    media = collect_media(ocr_results, rasterized, tmp_path, rebuild=True)

    assert [entry.media_id for entry in media] == ["illustration-001"]
    assert not leftover.exists()
    copied = media_dir / "illustration-001.png"
    assert copied.read_bytes() == (tmp_path / "source/pages/001.png").read_bytes()


def test_collect_media_without_rebuild_leaves_leftover_files(tmp_path: Path) -> None:
    """Default resume mode leaves existing prepared media files alone."""
    media_dir = tmp_path / "prepared" / "media"
    media_dir.mkdir(parents=True)
    leftover = media_dir / "illustration-013.png"
    leftover.write_bytes(PNG_BYTES + b"leftover")
    rasterized = _write_rasterized_pages(tmp_path, 2)
    ocr_results = [
        OcrPageResult(transcript="Text page", is_illustration=False),
        OcrPageResult(transcript="More text", is_illustration=False),
    ]

    media = collect_media(ocr_results, rasterized, tmp_path, rebuild=False)

    assert media == ()
    assert leftover.read_bytes() == PNG_BYTES + b"leftover"


def _write_rasterized_pages(volume_root: Path, count: int) -> list[RasterizedPage]:
    pages_dir = volume_root / "source" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    rasterized: list[RasterizedPage] = []
    for page in range(1, count + 1):
        path = pages_dir / f"{page:03d}.png"
        path.write_bytes(PNG_BYTES + bytes([page]) * 16)
        rasterized.append(RasterizedPage(page=page, path=path))
    return rasterized
