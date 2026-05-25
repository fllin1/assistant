"""Tests for the CLI interface."""

from unittest.mock import patch

from PIL import Image
from tests.conftest import make_fake_monitors, make_fake_screenshot
from typer.testing import CliRunner

from assistant.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "assistant" in result.stdout
    assert "0.1.0" in result.stdout


def test_help():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "capture" in result.stdout
    assert "monitors" in result.stdout


@patch("assistant.screen.mss.mss")
def test_monitors(mock_mss):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()

    result = runner.invoke(app, ["monitors"])

    assert result.exit_code == 0
    assert "combined" in result.stdout
    assert "monitor 1" in result.stdout
    assert "1920x1080" in result.stdout


@patch("assistant.screen.mss.mss")
def test_capture_saves_file(mock_mss, tmp_path):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()
    sct.grab.return_value = make_fake_screenshot(1920, 1080)

    result = runner.invoke(app, ["capture", "--output", str(tmp_path)])

    assert result.exit_code == 0
    assert "Saved:" in result.stdout
    # Verify a file was actually created
    saved_files = list(tmp_path.glob("*.png"))
    assert len(saved_files) == 1


@patch("assistant.screen.mss.mss")
def test_capture_with_grid(mock_mss, tmp_path):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()
    sct.grab.return_value = make_fake_screenshot(1920, 1080)

    result = runner.invoke(app, ["capture", "--grid", "--output", str(tmp_path)])

    assert result.exit_code == 0
    # Grid label should appear in filename
    saved_files = list(tmp_path.glob("*grid*.png"))
    assert len(saved_files) == 1


@patch("assistant.screen.mss.mss")
def test_capture_custom_label(mock_mss, tmp_path):
    sct = mock_mss.return_value.__enter__.return_value
    sct.monitors = make_fake_monitors()
    sct.grab.return_value = make_fake_screenshot(1920, 1080)

    result = runner.invoke(app, ["capture", "--label", "debug", "--output", str(tmp_path)])

    assert result.exit_code == 0
    saved_files = list(tmp_path.glob("*debug*.png"))
    assert len(saved_files) == 1


@patch("assistant.input.left_click")
@patch("assistant.screen.grid_to_screen_pixel", return_value=(1970, 50))
@patch("assistant.screen.capture_screen", return_value=Image.new("RGB", (1000, 800)))
def test_click_grid_cell_uses_absolute_screen_pixel(mock_capture, mock_grid, mock_click):
    result = runner.invoke(app, ["click", "A1", "--monitor", "2"])

    assert result.exit_code == 0
    mock_capture.assert_called_once_with(monitor=2)
    mock_grid.assert_called_once_with("A1", monitor=2, image_size=(1000, 800))
    mock_click.assert_called_once_with(1970, 50)
