"""Agent loop orchestrating capture → reason → act → verify.

The agent captures screenshots, sends them to a vision model for
analysis, executes the recommended actions, and logs each step
as an immutable record. Sessions persist as JSONL files.
"""

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from assistant.input import (
    double_click,
    left_click,
    mouse_move,
    press_key,
    right_click,
    scroll,
    type_text,
)
from assistant.screen import capture_screen, grid_to_pixel, save_capture
from assistant.vision import analyze_screenshot

logger = logging.getLogger(__name__)

DEFAULT_SESSIONS_DIR = Path.home() / ".assistant" / "sessions"


@dataclass(frozen=True)
class Action:
    """A single action decided by the vision model."""

    name: str
    target: str | None
    text: str | None
    pixel: tuple[int, int] | None


@dataclass(frozen=True)
class AgentStep:
    """One iteration of the agent loop. Immutable record."""

    step_number: int
    timestamp: float
    screenshot_path: str  # stored as string for JSON serialization
    reasoning: str
    action: Action
    success: bool


@dataclass
class Session:
    """A complete agent run. Mutable during execution."""

    session_id: str
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    outcome: str = "running"


# Seconds to wait after each action type, giving the UI time to respond
ACTION_DELAYS = {
    "left_click": 0.5,
    "right_click": 0.5,
    "double_click": 0.5,
    "type": 0.3,
    "key": 0.5,
    "mouse_move": 0.1,
    "scroll": 0.3,
}

STUCK_THRESHOLD = 3  # consecutive identical actions before aborting


def _is_stuck(steps: list[AgentStep]) -> bool:
    """Check if the agent is repeating the same action without progress."""
    if len(steps) < STUCK_THRESHOLD:
        return False
    recent = steps[-STUCK_THRESHOLD:]
    return all(
        s.action.name == recent[0].action.name and s.action.target == recent[0].action.target
        for s in recent
    )


def run_agent(
    task: str,
    max_iterations: int = 20,
    timeout_seconds: float = 300.0,
    monitor: int = 1,
    grid_cols: int = 10,
    grid_rows: int = 8,
    provider: str = "gemini",
    model: str | None = None,
    dry_run: bool = False,
) -> Session:
    """Run the agent loop to accomplish a task.

    Args:
        task: Natural language description of the task.
        max_iterations: Maximum number of loop iterations.
        timeout_seconds: Wall-clock timeout in seconds.
        monitor: Monitor index to capture.
        grid_cols: Grid columns for overlay.
        grid_rows: Grid rows for overlay.
        provider: Vision model provider.
        model: Model name override (default depends on provider).
        dry_run: If True, analyze but don't execute actions.

    Returns:
        Session with all steps and outcome.
    """
    session_id = _generate_session_id()
    session = Session(session_id=session_id, task=task)
    log_path = _session_log_path(session_id)

    # Write session header
    _append_jsonl(
        log_path,
        {
            "type": "session_start",
            "session_id": session_id,
            "task": task,
            "started_at": session.started_at,
            "dry_run": dry_run,
            "provider": provider,
            "model": model,
        },
    )

    logger.info("Agent session %s started: %s", session_id[:8], task)
    if dry_run:
        logger.info("DRY RUN — actions will not be executed")

    start_time = session.started_at

    for i in range(max_iterations):
        # Check timeout
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            session.outcome = "timeout"
            logger.info("Session timed out after %.1fs", elapsed)
            break

        # Capture
        screenshot = capture_screen(monitor=monitor)
        screenshot_path = save_capture(screenshot, label=f"step_{i}")

        # Build history from recent steps (last 5)
        history = _build_history(session.steps[-5:])

        # Reason
        response = analyze_screenshot(
            screenshot,
            task=task,
            history=history,
            provider=provider,
            model=model,
            grid_cols=grid_cols,
            grid_rows=grid_rows,
        )

        # Check for completion
        if response.action == "done":
            action = Action(name="done", target=None, text=None, pixel=None)
            step = AgentStep(
                step_number=i,
                timestamp=time.time(),
                screenshot_path=str(screenshot_path),
                reasoning=response.reasoning,
                action=action,
                success=True,
            )
            session.steps.append(step)
            _append_jsonl(log_path, _step_to_dict(step))
            session.outcome = "completed"
            logger.info("Task completed at step %d: %s", i, response.reasoning)
            break

        # Resolve grid reference to pixel coordinates
        pixel = None
        if response.target:
            pixel = grid_to_pixel(response.target, screenshot.size, grid_cols, grid_rows)

        action = Action(
            name=response.action,
            target=response.target,
            text=response.text,
            pixel=pixel,
        )

        # Act (unless dry run)
        success = True
        if not dry_run:
            try:
                _execute(action)
                # Wait for the UI to respond before taking the next screenshot
                delay = ACTION_DELAYS.get(action.name, 0.3)
                time.sleep(delay)
            except Exception:
                logger.exception("Action failed at step %d", i)
                success = False

        step = AgentStep(
            step_number=i,
            timestamp=time.time(),
            screenshot_path=str(screenshot_path),
            reasoning=response.reasoning,
            action=action,
            success=success,
        )
        session.steps.append(step)
        _append_jsonl(log_path, _step_to_dict(step))

        logger.info(
            "Step %d: %s %s — %s",
            i,
            action.name,
            action.target or action.text or "",
            response.reasoning[:80],
        )

        # Detect if the agent is stuck repeating the same action
        if _is_stuck(session.steps):
            session.outcome = "stuck"
            logger.info(
                "Agent stuck: repeated %s %s %d times",
                action.name,
                action.target or "",
                STUCK_THRESHOLD,
            )
            break
    else:
        session.outcome = "max_iterations"
        logger.info("Reached max iterations (%d)", max_iterations)

    session.ended_at = time.time()

    # Write session footer
    _append_jsonl(
        log_path,
        {
            "type": "session_end",
            "session_id": session_id,
            "outcome": session.outcome,
            "total_steps": len(session.steps),
            "ended_at": session.ended_at,
            "duration_seconds": session.ended_at - session.started_at,
        },
    )

    logger.info(
        "Session %s ended: %s (%d steps, %.1fs)",
        session_id[:8],
        session.outcome,
        len(session.steps),
        session.ended_at - session.started_at,
    )

    return session


def _generate_session_id() -> str:
    return uuid.uuid4().hex[:12]


def _session_log_path(session_id: str) -> Path:
    """Generate the JSONL log file path for a session."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    directory = DEFAULT_SESSIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{timestamp}_{session_id}.jsonl"


def _append_jsonl(path: Path, data: dict) -> None:
    """Append one JSON line to a file."""
    with path.open("a") as f:
        f.write(json.dumps(data, default=str) + "\n")


def _step_to_dict(step: AgentStep) -> dict:
    """Convert an AgentStep to a serializable dict."""
    d = asdict(step)
    d["type"] = "step"
    return d


def _build_history(steps: list[AgentStep]) -> list[dict] | None:
    """Format recent steps as history for the vision model."""
    if not steps:
        return None
    return [
        {
            "action": s.action.name,
            "target": s.action.target,
            "reasoning": s.reasoning,
        }
        for s in steps
    ]


def _execute(action: Action) -> None:
    """Execute an action by calling input functions directly."""
    x, y = action.pixel if action.pixel else (0, 0)

    match action.name:
        case "left_click":
            left_click(x, y)
        case "right_click":
            right_click(x, y)
        case "double_click":
            double_click(x, y)
        case "mouse_move":
            mouse_move(x, y)
        case "type":
            type_text(action.text or "")
        case "key":
            press_key(action.text or "")
        case "scroll":
            direction = action.text or "down"
            scroll(x, y, direction=direction)
        case _:
            raise ValueError(f"Unknown action: {action.name}")
