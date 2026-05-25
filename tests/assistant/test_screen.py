"""Tests for the screen capture module."""

import re
from datetime import datetime
from unittest.mock import patch

import pytest
from PIL import Image
from tests.conftest import make_fake_monitors, make_fake_screenshot

from assistant.screen import (
    DEFAULT_CAPTURES_DIR,
    capture_region,
    capture_screen,
    get_monitor_geometry,
    grid_to_pixel,
    grid_to_screen_pixel,
    list_monitors,
    overlay_grid,
    save_capture,
)

# -- capture_screen --


@patch("assistant.screen.mss.mss")
def test_capture_screen_returns_rgb_image(mock_mss):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()
    sct.grab.return_value = make_fake_screenshot(1920, 1080)

    result = capture_screen(monitor=1)

    assert isinstance(result, Image.Image)
    assert result.mode == "RGB"
    assert result.size == (1920, 1080)


@patch("assistant.screen.mss.mss")
def test_capture_screen_default_monitor(mock_mss):
    """Default monitor captures the primary display."""
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()
    sct.grab.return_value = make_fake_screenshot(1920, 1080)

    capture_screen()

    sct.grab.assert_called_once_with(sct.monitors[1])


@patch("assistant.screen.mss.mss")
def test_capture_screen_rejects_invalid_monitor(mock_mss):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()

    with pytest.raises(ValueError, match="Monitor index 9 is out of range"):
        capture_screen(monitor=9)


# -- capture_region --


@patch("assistant.screen.mss.mss")
def test_capture_region_returns_correct_size(mock_mss):
    sct = mock_mss.return_value.__enter__.return_value
    sct.grab.return_value = make_fake_screenshot(200, 150)

    result = capture_region(x=100, y=100, width=200, height=150)

    assert isinstance(result, Image.Image)
    assert result.mode == "RGB"
    assert result.size == (200, 150)
    sct.grab.assert_called_once_with({"left": 100, "top": 100, "width": 200, "height": 150})


# -- list_monitors --


@patch("assistant.screen.mss.mss")
def test_list_monitors_returns_list(mock_mss):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()

    result = list_monitors()

    assert isinstance(result, list)
    assert len(result) == 3
    for m in result:
        assert isinstance(m, dict)
        assert set(m.keys()) >= {"left", "top", "width", "height"}


@patch("assistant.screen.mss.mss")
def test_get_monitor_geometry_returns_absolute_position(mock_mss):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()

    result = get_monitor_geometry(2)

    assert result == {"left": 1920, "top": 0, "width": 1920, "height": 1080}


# -- save_capture --


def test_save_capture_creates_file(tmp_path):
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))

    path = save_capture(img, label="test", directory=tmp_path)

    assert path.exists()
    assert path.suffix == ".png"
    # Verify the saved image is readable
    saved = Image.open(path)
    assert saved.size == (100, 100)


def test_save_capture_naming_convention(tmp_path):
    img = Image.new("RGB", (100, 100))

    path = save_capture(img, label="my_label", directory=tmp_path)

    # Expected pattern: HHMMSS_my_label.png
    assert re.match(r"\d{6}_my_label\.png$", path.name)


def test_save_capture_custom_directory(tmp_path):
    custom_dir = tmp_path / "custom"
    img = Image.new("RGB", (100, 100))

    path = save_capture(img, directory=custom_dir)

    assert path.parent == custom_dir
    assert custom_dir.exists()


def test_save_capture_default_directory(monkeypatch):
    """When no directory is given, saves to ~/.assistant/captures/{date}/."""
    img = Image.new("RGB", (10, 10))
    today = datetime.now().strftime("%Y-%m-%d")

    path = save_capture(img, label="default_test")

    expected_dir = DEFAULT_CAPTURES_DIR / today
    assert path.parent == expected_dir
    assert path.exists()

    # Clean up the file we created
    path.unlink()
    # Only remove directory if empty (don't break other captures)
    if not any(expected_dir.iterdir()):
        expected_dir.rmdir()


# -- Live integration test --


@pytest.mark.live
def test_live_capture():
    """Capture real screen — requires a display. Run with: pytest -m live"""
    img = capture_screen()

    assert isinstance(img, Image.Image)
    assert img.mode == "RGB"
    assert img.size[0] > 0
    assert img.size[1] > 0


# -- overlay_grid --


def test_overlay_grid_returns_new_image():
    """Input image is not modified; a new image is returned."""
    original = Image.new("RGB", (1024, 768), color=(100, 100, 100))
    original_data = original.tobytes()

    result = overlay_grid(original)

    assert result is not original
    assert original.tobytes() == original_data  # input unchanged


def test_overlay_grid_same_size():
    img = Image.new("RGB", (1024, 768))

    result = overlay_grid(img, cols=10, rows=8)

    assert result.size == img.size


# -- grid_to_pixel --


def test_grid_to_pixel_top_left():
    """A1 should map to the center of the top-left cell."""
    x, y = grid_to_pixel("A1", image_size=(1000, 800), cols=10, rows=8)

    # Cell is 100x100, center should be (50, 50)
    assert x == 50
    assert y == 50


def test_grid_to_pixel_last_cell():
    """J8 should map to the center of the bottom-right cell."""
    x, y = grid_to_pixel("J8", image_size=(1000, 800), cols=10, rows=8)

    # Last cell center at 10x8 grid on 1000x800 image
    assert x == 950
    assert y == 750


def test_grid_to_pixel_middle():
    """E4 should map roughly to the center of the image."""
    x, y = grid_to_pixel("E4", image_size=(1000, 800), cols=10, rows=8)

    # Col E = index 4, row 4 = index 3
    # (4 * 100 + 50, 3 * 100 + 50) = (450, 350)
    assert x == 450
    assert y == 350


def test_grid_to_pixel_case_insensitive():
    """Grid references should work with lowercase letters."""
    upper = grid_to_pixel("B2", image_size=(1000, 800))
    lower = grid_to_pixel("b2", image_size=(1000, 800))

    assert upper == lower


def test_grid_to_pixel_rejects_invalid_cell():
    with pytest.raises(ValueError, match="Invalid grid cell"):
        grid_to_pixel("AA1", image_size=(1000, 800))


def test_grid_to_pixel_rejects_out_of_range_cell():
    with pytest.raises(ValueError, match="outside A1-J8"):
        grid_to_pixel("K1", image_size=(1000, 800), cols=10, rows=8)


def test_overlay_grid_rejects_too_many_columns():
    img = Image.new("RGB", (100, 100))

    with pytest.raises(ValueError, match="cannot exceed 26"):
        overlay_grid(img, cols=27, rows=8)


@patch("assistant.screen.mss.mss")
def test_grid_to_screen_pixel_adds_monitor_offset(mock_mss):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()

    x, y = grid_to_screen_pixel("A1", monitor=2, image_size=(1000, 800), cols=10, rows=8)

    assert (x, y) == (1970, 50)
