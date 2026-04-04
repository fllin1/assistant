"""Tests for the screen capture module."""

import re
from datetime import datetime
from unittest.mock import patch

import pytest
from PIL import Image

from assistant.screen import (
    DEFAULT_CAPTURES_DIR,
    capture_region,
    capture_screen,
    list_monitors,
    save_capture,
)
from tests.conftest import make_fake_monitors, make_fake_screenshot

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
    """Default monitor=0 captures the combined virtual screen."""
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()
    sct.grab.return_value = make_fake_screenshot(3840, 1080)

    capture_screen()

    sct.grab.assert_called_once_with(sct.monitors[0])


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
