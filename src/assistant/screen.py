"""Screen capture utilities using mss.

Provides functions to capture screenshots, list monitors, and save images.
All capture functions return PIL Images in RGB format. mss captures in BGRA
internally — the conversion happens here so callers never deal with it.
"""

import logging
from datetime import datetime
from pathlib import Path

import mss
from PIL import Image

logger = logging.getLogger(__name__)

# Default save location for captures, outside the repo
DEFAULT_CAPTURES_DIR = Path.home() / ".assistant" / "captures"


def capture_screen(monitor: int = 0) -> Image.Image:
    """Capture a full monitor.

    Args:
        monitor: Monitor index. 0 captures all monitors combined,
            1 is the primary monitor, 2+ for additional monitors.

    Returns:
        PIL Image in RGB format.
    """
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[monitor])
        # mss returns BGRA; convert to RGB via BGRX (ignore alpha)
        img = Image.frombytes("RGB", raw.size, raw.rgb)
        logger.debug("Captured monitor %d: %dx%d", monitor, img.width, img.height)
        return img


def capture_region(x: int, y: int, width: int, height: int) -> Image.Image:
    """Capture a rectangular region of the screen.

    Coordinates are absolute across the virtual desktop
    (all monitors combined).

    Args:
        x: Left edge in pixels.
        y: Top edge in pixels.
        width: Width in pixels.
        height: Height in pixels.

    Returns:
        PIL Image in RGB format.
    """
    region = {"left": x, "top": y, "width": width, "height": height}
    with mss.mss() as sct:
        raw = sct.grab(region)
        img = Image.frombytes("RGB", raw.size, raw.rgb)
        logger.debug("Captured region (%d,%d) %dx%d", x, y, width, height)
        return img


def list_monitors() -> list[dict[str, int]]:
    """List available monitors and their geometry.

    Returns:
        List of dicts with keys: left, top, width, height.
        Index 0 is the combined virtual screen.
        Index 1+ are individual monitors.
    """
    with mss.mss() as sct:
        return [dict(m) for m in sct.monitors]


def save_capture(
    image: Image.Image,
    label: str = "full",
    directory: Path | None = None,
) -> Path:
    """Save a PIL Image with auto-generated naming.

    Files are saved as: {HHMMSS}_{label}.png in a date-partitioned directory.

    Args:
        image: The image to save.
        label: Descriptive label included in the filename.
        directory: Override the save directory. Defaults to
            ~/.assistant/captures/{YYYY-MM-DD}/.

    Returns:
        The path where the image was saved.
    """
    now = datetime.now()

    if directory is None:
        directory = DEFAULT_CAPTURES_DIR / now.strftime("%Y-%m-%d")

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    filename = f"{now.strftime('%H%M%S')}_{label}.png"
    path = directory / filename
    image.save(path)
    logger.debug("Saved capture to %s", path)
    return path
