"""AnyFlip downloader CLI boundary for the LNVO v2 prepare stage."""

from __future__ import annotations

import subprocess
from pathlib import Path


def download_anyflip(
    url: str,
    dest_pdf: Path,
    *,
    executable: str = "anyflip-downloader",
    timeout_seconds: int = 600,
) -> Path:
    """Download an AnyFlip flipbook to a single PDF.

    Args:
        url: AnyFlip flipbook URL.
        dest_pdf: Destination PDF path.
        executable: Downloader CLI executable name or path.
        timeout_seconds: Subprocess timeout in seconds.

    Returns:
        The destination PDF path.

    Raises:
        RuntimeError: If the downloader exits non-zero or produces no PDF.
    """
    if dest_pdf.exists() and dest_pdf.stat().st_size > 0:
        return dest_pdf

    dest_pdf.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [executable, "--url", url, "--output", str(dest_pdf)],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)
    if not dest_pdf.is_file() or dest_pdf.stat().st_size <= 0:
        raise RuntimeError("anyflip-downloader exited 0 but produced no PDF: " + completed.stderr)
    return dest_pdf
