"""Tests for the AnyFlip downloader boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from automations.ln_voice_over_v2.stages.prepare.downloader import download_anyflip


def test_download_anyflip_invokes_cli_and_returns_pdf(tmp_path: Path) -> None:
    """The downloader shells out with the locked argv shape."""
    dest_pdf = tmp_path / "source" / "volume.pdf"

    def complete_download(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        dest_pdf.write_bytes(b"%PDF-1.7")
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch(
        "automations.ln_voice_over_v2.stages.prepare.downloader.subprocess.run",
        side_effect=complete_download,
    ) as run:
        assert (
            download_anyflip(
                "https://anyflip.example/book",
                dest_pdf,
                executable="downloader-test",
                timeout_seconds=7,
            )
            == dest_pdf
        )

    run.assert_called_once_with(
        [
            "downloader-test",
            "-title",
            dest_pdf.stem,
            "https://anyflip.example/book",
        ],
        cwd=dest_pdf.parent,
        capture_output=True,
        text=True,
        timeout=7,
    )


def test_download_anyflip_raises_on_nonzero_exit(tmp_path: Path) -> None:
    """A non-zero downloader exit raises with stderr."""
    dest_pdf = tmp_path / "volume.pdf"
    completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="failed")

    with (
        pytest.raises(RuntimeError, match="failed"),
        patch(
            "automations.ln_voice_over_v2.stages.prepare.downloader.subprocess.run",
            return_value=completed,
        ),
    ):
        download_anyflip("https://anyflip.example/book", dest_pdf)

    assert not dest_pdf.exists()


def test_download_anyflip_raises_when_output_is_missing(tmp_path: Path) -> None:
    """A zero-exit downloader still has to produce a non-empty PDF."""
    dest_pdf = tmp_path / "volume.pdf"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="no output")

    with (
        pytest.raises(RuntimeError, match=r"produced no PDF at .*: no output"),
        patch(
            "automations.ln_voice_over_v2.stages.prepare.downloader.subprocess.run",
            return_value=completed,
        ),
    ):
        download_anyflip("https://anyflip.example/book", dest_pdf)


def test_download_anyflip_skips_existing_non_empty_pdf(tmp_path: Path) -> None:
    """Existing non-empty PDFs are reused without invoking the CLI."""
    dest_pdf = tmp_path / "volume.pdf"
    dest_pdf.write_bytes(b"%PDF-1.7")

    with patch("automations.ln_voice_over_v2.stages.prepare.downloader.subprocess.run") as run:
        assert download_anyflip("https://anyflip.example/book", dest_pdf) == dest_pdf

    run.assert_not_called()
