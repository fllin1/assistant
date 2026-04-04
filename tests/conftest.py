"""Shared test fixtures and helpers."""

from unittest.mock import MagicMock


def make_fake_screenshot(width: int = 100, height: int = 50) -> MagicMock:
    """Create a fake mss screenshot object with valid RGB data."""
    mock = MagicMock()
    mock.size = (width, height)
    # 3 bytes per pixel (RGB) for the .rgb property
    mock.rgb = bytes([128, 64, 32] * width * height)
    return mock


def make_fake_monitors() -> list[dict[str, int]]:
    """Standard multi-monitor setup for testing."""
    return [
        {"left": 0, "top": 0, "width": 3840, "height": 1080},  # combined
        {"left": 0, "top": 0, "width": 1920, "height": 1080},  # monitor 1
        {"left": 1920, "top": 0, "width": 1920, "height": 1080},  # monitor 2
    ]
