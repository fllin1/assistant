"""Tests for the input control module."""

from unittest.mock import MagicMock, patch

import pytest

from assistant.input import (
    double_click,
    execute_action,
    left_click,
    mouse_move,
    press_key,
    right_click,
    scroll,
    type_text,
)


@pytest.fixture()
def mock_pag():
    """Mock pyautogui via the lazy loader."""
    pag = MagicMock()
    with patch("assistant.input._get_pyautogui", return_value=pag):
        yield pag


# -- Click functions --


def test_left_click_calls_pyautogui(mock_pag):
    left_click(100, 200)
    mock_pag.click.assert_called_once_with(100, 200, button="left")


def test_right_click_calls_pyautogui(mock_pag):
    right_click(300, 400)
    mock_pag.click.assert_called_once_with(300, 400, button="right")


def test_double_click_calls_pyautogui(mock_pag):
    double_click(500, 600)
    mock_pag.doubleClick.assert_called_once_with(500, 600)


def test_mouse_move_calls_pyautogui(mock_pag):
    mouse_move(100, 100)
    mock_pag.moveTo.assert_called_once_with(100, 100)


# -- Type and key --


def test_type_text_calls_pyautogui(mock_pag):
    type_text("hello world")
    mock_pag.write.assert_called_once_with("hello world", interval=0.02)


def test_press_key_single(mock_pag):
    """Single key like 'enter' uses pyautogui.press."""
    press_key("enter")
    mock_pag.press.assert_called_once_with("enter")


def test_press_key_hotkey(mock_pag):
    """Combo like 'ctrl+s' splits and uses pyautogui.hotkey."""
    press_key("ctrl+s")
    mock_pag.hotkey.assert_called_once_with("ctrl", "s")


def test_press_key_triple_combo(mock_pag):
    """Three-key combo like 'ctrl+shift+s'."""
    press_key("ctrl+shift+s")
    mock_pag.hotkey.assert_called_once_with("ctrl", "shift", "s")


# -- Scroll --


def test_scroll_down(mock_pag):
    scroll(100, 200, direction="down", amount=5)
    mock_pag.scroll.assert_called_once_with(-5, x=100, y=200)


def test_scroll_up(mock_pag):
    scroll(100, 200, direction="up", amount=3)
    mock_pag.scroll.assert_called_once_with(3, x=100, y=200)


# -- execute_action dispatcher --


def test_execute_action_dispatches_click(mock_pag):
    execute_action("left_click", x=100, y=200)
    mock_pag.click.assert_called_once_with(100, 200, button="left")


def test_execute_action_dispatches_type(mock_pag):
    execute_action("type", text="hello")
    mock_pag.write.assert_called_once_with("hello", interval=0.02)


def test_execute_action_dispatches_key(mock_pag):
    execute_action("key", keys="enter")
    mock_pag.press.assert_called_once_with("enter")


def test_execute_action_invalid_raises():
    with pytest.raises(ValueError, match="Unknown action"):
        execute_action("explode", x=0, y=0)
