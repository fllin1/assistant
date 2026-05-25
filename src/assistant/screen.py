"""Screen capture and annotation utilities.

Provides functions to capture screenshots, list monitors, save images,
and annotate screenshots with grid overlays for model-friendly targeting.
All capture functions return PIL Images in RGB format. mss captures in BGRA
internally — the conversion happens here so callers never deal with it.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import mss
from PIL import Image, ImageDraw, ImageFont

from assistant.config import DEFAULT_MONITOR

logger = logging.getLogger(__name__)

# Default save location for captures, outside the repo
DEFAULT_CAPTURES_DIR = Path.home() / ".assistant" / "captures"


def capture_screen(monitor: int = DEFAULT_MONITOR) -> Image.Image:
    """Capture a full monitor.

    Args:
        monitor: Monitor index. 0 captures all monitors combined,
            1 is the primary monitor, 2+ for additional monitors.

    Returns:
        PIL Image in RGB format.
    """
    with mss.mss() as sct:
        geometry = _select_monitor(sct.monitors, monitor)
        raw = sct.grab(geometry)
        # mss returns BGRA; convert to RGB via BGRX (ignore alpha)
        img = Image.frombytes("RGB", raw.size, raw.rgb)
        logger.debug(
            "Captured monitor %d at (%d,%d): %dx%d",
            monitor,
            geometry["left"],
            geometry["top"],
            img.width,
            img.height,
        )
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


def get_monitor_geometry(monitor: int = DEFAULT_MONITOR) -> dict[str, int]:
    """Return absolute desktop geometry for a monitor index.

    mss uses index 0 for the combined virtual desktop. PyAutoGUI coordinates are
    absolute, so callers that convert screenshot-local positions must add this
    offset before acting on the real screen.
    """
    with mss.mss() as sct:
        return _select_monitor(sct.monitors, monitor)


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


def overlay_grid(
    image: Image.Image,
    cols: int = 10,
    rows: int = 8,
) -> Image.Image:
    """Draw a labeled grid over a screenshot for model-friendly targeting.

    Each cell is labeled with a column letter + row number (e.g., A1, B3, J8).
    The model references cells instead of guessing raw pixel coordinates.

    This is an experimental targeting approach — one of several to be evaluated.

    Args:
        image: The screenshot to annotate.
        cols: Number of columns (max 26, labeled A-Z).
        rows: Number of rows (labeled 1-N).

    Returns:
        A new image with the grid overlay. The input is not modified.
    """
    _validate_grid_dimensions(cols, rows)

    annotated = image.copy()
    draw = ImageDraw.Draw(annotated, "RGBA")
    w, h = annotated.size
    cell_w = w / cols
    cell_h = h / rows

    # Semi-transparent grid lines
    line_color = (255, 255, 255, 80)
    for col in range(1, cols):
        x = int(col * cell_w)
        draw.line([(x, 0), (x, h)], fill=line_color, width=1)
    for row in range(1, rows):
        y = int(row * cell_h)
        draw.line([(0, y), (w, y)], fill=line_color, width=1)

    # Cell labels — small text at top-left of each cell
    # Use default font; a proper font can be configured later
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except OSError:
        font = ImageFont.load_default()

    label_bg = (0, 0, 0, 140)
    label_fg = (255, 255, 255, 220)

    for col in range(cols):
        for row in range(rows):
            label = f"{chr(65 + col)}{row + 1}"
            x = int(col * cell_w) + 2
            y = int(row * cell_h) + 1

            # Draw a small background rectangle for readability
            bbox = font.getbbox(label)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            draw.rectangle([x, y, x + text_w + 4, y + text_h + 2], fill=label_bg)
            draw.text((x + 2, y), label, fill=label_fg, font=font)

    logger.debug("Overlaid %dx%d grid on %dx%d image", cols, rows, w, h)
    return annotated


def grid_to_pixel(
    cell: str,
    image_size: tuple[int, int],
    cols: int = 10,
    rows: int = 8,
) -> tuple[int, int]:
    """Convert a grid cell reference to pixel coordinates.

    Returns the center of the specified cell. Used to map model output
    (e.g., "B3") to a click target.

    Args:
        cell: Grid reference like "A1", "B3", "J8". Column is a letter, row is a number.
        image_size: (width, height) of the image the grid was drawn on.
        cols: Number of columns (must match the grid that was drawn).
        rows: Number of rows (must match the grid that was drawn).

    Returns:
        (x, y) pixel coordinates at the center of the cell.
    """
    col_index, row_index = _parse_grid_cell(cell, cols, rows)

    w, h = image_size
    cell_w = w / cols
    cell_h = h / rows

    x = int(col_index * cell_w + cell_w / 2)
    y = int(row_index * cell_h + cell_h / 2)

    return (x, y)


def grid_to_screen_pixel(
    cell: str,
    monitor: int,
    image_size: tuple[int, int],
    cols: int = 10,
    rows: int = 8,
) -> tuple[int, int]:
    """Convert a grid cell reference to absolute screen coordinates."""
    local_x, local_y = grid_to_pixel(cell, image_size, cols=cols, rows=rows)
    geometry = get_monitor_geometry(monitor)
    return (geometry["left"] + local_x, geometry["top"] + local_y)


def _select_monitor(monitors: list[Any], monitor: int) -> dict[str, int]:
    if monitor < 0 or monitor >= len(monitors):
        available = f"0-{len(monitors) - 1}"
        raise ValueError(f"Monitor index {monitor} is out of range. Available: {available}")
    return dict(monitors[monitor])


def _validate_grid_dimensions(cols: int, rows: int) -> None:
    if cols < 1 or rows < 1:
        raise ValueError("Grid dimensions must be positive")
    if cols > 26:
        raise ValueError("Grid columns cannot exceed 26 with A-Z labels")


def _parse_grid_cell(cell: str, cols: int, rows: int) -> tuple[int, int]:
    _validate_grid_dimensions(cols, rows)

    normalized = cell.strip()
    if len(normalized) < 2 or not normalized[0].isalpha() or not normalized[1:].isdigit():
        raise ValueError(f"Invalid grid cell: {cell!r}")

    col_index = ord(normalized[0].upper()) - ord("A")
    row_index = int(normalized[1:]) - 1

    if col_index < 0 or col_index >= cols or row_index < 0 or row_index >= rows:
        max_cell = f"{chr(64 + cols)}{rows}"
        raise ValueError(f"Grid cell {cell!r} is outside A1-{max_cell}")

    return col_index, row_index
