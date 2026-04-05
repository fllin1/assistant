"""Mouse and keyboard control via PyAutoGUI.

Thin wrappers around pyautogui with debug logging and a dispatcher
for the agent loop. All coordinate functions expect absolute pixel
positions — grid-to-pixel conversion happens in the caller.

PyAutoGUI is imported lazily to avoid X11 connection attempts at
module load time — this lets the module be imported and tested on
headless systems (like WSL2) as long as functions aren't called.
"""

import logging

logger = logging.getLogger(__name__)

# Valid action names for the dispatcher
ACTION_VOCABULARY = frozenset(
    {
        "left_click",
        "right_click",
        "double_click",
        "mouse_move",
        "type",
        "key",
        "scroll",
    }
)


def _get_pyautogui():
    """Lazy import of pyautogui. Enables failsafe on first load."""
    import pyautogui

    pyautogui.FAILSAFE = True
    return pyautogui


def left_click(x: int, y: int) -> None:
    """Left-click at the given pixel coordinates."""
    logger.debug("left_click(%d, %d)", x, y)
    _get_pyautogui().click(x, y, button="left")


def right_click(x: int, y: int) -> None:
    """Right-click at the given pixel coordinates."""
    logger.debug("right_click(%d, %d)", x, y)
    _get_pyautogui().click(x, y, button="right")


def double_click(x: int, y: int) -> None:
    """Double-click at the given pixel coordinates."""
    logger.debug("double_click(%d, %d)", x, y)
    _get_pyautogui().doubleClick(x, y)


def mouse_move(x: int, y: int) -> None:
    """Move the mouse cursor to the given pixel coordinates."""
    logger.debug("mouse_move(%d, %d)", x, y)
    _get_pyautogui().moveTo(x, y)


def type_text(text: str) -> None:
    """Type text at the current cursor position."""
    logger.debug("type_text(%r)", text)
    _get_pyautogui().write(text, interval=0.02)


def press_key(keys: str) -> None:
    """Press a key or key combination.

    Args:
        keys: Single key ("enter") or combo ("ctrl+s").
            Combos are split on "+" and passed to pyautogui.hotkey.
    """
    pag = _get_pyautogui()
    parts = [k.strip() for k in keys.split("+")]
    if len(parts) == 1:
        logger.debug("press_key(%r)", parts[0])
        pag.press(parts[0])
    else:
        logger.debug("hotkey(%s)", ", ".join(repr(k) for k in parts))
        pag.hotkey(*parts)


def scroll(x: int, y: int, direction: str = "down", amount: int = 3) -> None:
    """Scroll at the given position.

    Args:
        x: Horizontal pixel position.
        y: Vertical pixel position.
        direction: "up" or "down".
        amount: Number of scroll clicks.
    """
    clicks = amount if direction == "up" else -amount
    logger.debug("scroll(%d, %d, %s, %d)", x, y, direction, amount)
    _get_pyautogui().scroll(clicks, x=x, y=y)


def execute_action(action: str, **kwargs) -> None:
    """Dispatch an action by name. Called by the agent loop.

    Args:
        action: Action name from the vocabulary (e.g., "left_click", "type").
        **kwargs: Arguments forwarded to the corresponding function.
            Click actions: x, y
            type: text
            key: keys
            scroll: x, y, direction, amount

    Raises:
        ValueError: If action is not in the vocabulary.
    """
    if action not in ACTION_VOCABULARY:
        raise ValueError(f"Unknown action: {action!r}. Valid: {sorted(ACTION_VOCABULARY)}")

    dispatch = {
        "left_click": lambda: left_click(kwargs["x"], kwargs["y"]),
        "right_click": lambda: right_click(kwargs["x"], kwargs["y"]),
        "double_click": lambda: double_click(kwargs["x"], kwargs["y"]),
        "mouse_move": lambda: mouse_move(kwargs["x"], kwargs["y"]),
        "type": lambda: type_text(kwargs["text"]),
        "key": lambda: press_key(kwargs["keys"]),
        "scroll": lambda: scroll(
            kwargs["x"],
            kwargs["y"],
            kwargs.get("direction", "down"),
            kwargs.get("amount", 3),
        ),
    }

    dispatch[action]()
