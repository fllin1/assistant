"""Tests for the agent loop."""

import json
import time
from unittest.mock import patch

import pytest
from PIL import Image

from assistant.agent import (
    Action,
    AgentStep,
    run_agent,
)
from assistant.vision import VisionResponse


@pytest.fixture()
def mock_screen():
    """Mock screen capture to return a fake image."""
    img = Image.new("RGB", (1024, 768))
    with (
        patch("assistant.agent.capture_screen", return_value=img),
        patch("assistant.agent.save_capture", return_value="/tmp/fake.png"),
    ):
        yield img


@pytest.fixture()
def mock_input():
    """Mock input module so no real clicks happen."""
    with patch("assistant.agent.execute_action") as mock:
        yield mock


def _make_vision_response(action="done", target=None, text=None):
    return VisionResponse(
        reasoning="test reasoning",
        action=action,
        target=target,
        text=text,
        confidence="high",
    )


# -- Agent loop behavior --


def test_run_agent_completes_on_done(mock_screen, mock_input, tmp_path):
    with (
        patch("assistant.agent.analyze_screenshot", return_value=_make_vision_response("done")),
        patch("assistant.agent.DEFAULT_SESSIONS_DIR", tmp_path),
    ):
        session = run_agent("test task", max_iterations=10)

    assert session.outcome == "completed"
    assert len(session.steps) == 1
    assert session.steps[0].action.name == "done"


def test_run_agent_executes_click(mock_screen, mock_input, tmp_path):
    responses = [
        _make_vision_response("left_click", target="B3"),
        _make_vision_response("done"),
    ]
    call_count = iter(responses)

    with (
        patch("assistant.agent.analyze_screenshot", side_effect=call_count),
        patch("assistant.agent.DEFAULT_SESSIONS_DIR", tmp_path),
    ):
        session = run_agent("click something", max_iterations=10)

    assert session.outcome == "completed"
    assert len(session.steps) == 2
    assert session.steps[0].action.name == "left_click"
    assert session.steps[0].action.target == "B3"
    assert session.steps[0].action.pixel is not None
    mock_input.assert_called_once()


def test_run_agent_respects_max_iterations(mock_screen, mock_input, tmp_path):
    with (
        patch(
            "assistant.agent.analyze_screenshot",
            return_value=_make_vision_response("left_click", target="A1"),
        ),
        patch("assistant.agent.DEFAULT_SESSIONS_DIR", tmp_path),
    ):
        session = run_agent("endless task", max_iterations=3)

    assert session.outcome == "max_iterations"
    assert len(session.steps) == 3


def test_run_agent_respects_timeout(mock_screen, mock_input, tmp_path):
    """Mock time to simulate timeout."""
    real_time = time.time
    call_count = 0

    def fake_time():
        nonlocal call_count
        call_count += 1
        # First call is session start, after that advance 1000s per call
        if call_count <= 2:
            return real_time()
        return real_time() + 1000

    with (
        patch("assistant.agent.time.time", side_effect=fake_time),
        patch(
            "assistant.agent.analyze_screenshot",
            return_value=_make_vision_response("left_click", target="A1"),
        ),
        patch("assistant.agent.DEFAULT_SESSIONS_DIR", tmp_path),
    ):
        session = run_agent("timeout task", max_iterations=100, timeout_seconds=5.0)

    assert session.outcome == "timeout"


def test_run_agent_dry_run(mock_screen, mock_input, tmp_path):
    responses = [
        _make_vision_response("left_click", target="B3"),
        _make_vision_response("done"),
    ]

    with (
        patch("assistant.agent.analyze_screenshot", side_effect=iter(responses)),
        patch("assistant.agent.DEFAULT_SESSIONS_DIR", tmp_path),
    ):
        session = run_agent("dry run task", dry_run=True)

    assert session.outcome == "completed"
    # execute_action should never be called in dry run
    mock_input.assert_not_called()


# -- Session logging --


def test_session_logging_creates_file(mock_screen, mock_input, tmp_path):
    with (
        patch("assistant.agent.analyze_screenshot", return_value=_make_vision_response("done")),
        patch("assistant.agent.DEFAULT_SESSIONS_DIR", tmp_path),
    ):
        run_agent("logging test")

    jsonl_files = list(tmp_path.glob("*.jsonl"))
    assert len(jsonl_files) == 1


def test_session_logging_format(mock_screen, mock_input, tmp_path):
    with (
        patch("assistant.agent.analyze_screenshot", return_value=_make_vision_response("done")),
        patch("assistant.agent.DEFAULT_SESSIONS_DIR", tmp_path),
    ):
        run_agent("format test")

    jsonl_file = next(tmp_path.glob("*.jsonl"))
    lines = jsonl_file.read_text().strip().split("\n")

    # Should have: session_start, one step, session_end
    assert len(lines) == 3
    for line in lines:
        data = json.loads(line)
        assert "type" in data

    assert json.loads(lines[0])["type"] == "session_start"
    assert json.loads(lines[1])["type"] == "step"
    assert json.loads(lines[2])["type"] == "session_end"


# -- Dataclass behavior --


def test_agent_step_is_frozen():
    step = AgentStep(
        step_number=0,
        timestamp=0.0,
        screenshot_path="/tmp/test.png",
        reasoning="test",
        action=Action(name="done", target=None, text=None, pixel=None),
        success=True,
    )
    with pytest.raises(AttributeError):
        step.success = False


def test_action_is_frozen():
    action = Action(name="left_click", target="B3", text=None, pixel=(100, 200))
    with pytest.raises(AttributeError):
        action.name = "right_click"
