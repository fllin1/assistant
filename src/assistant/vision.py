"""Vision model integration for screen analysis.

Sends annotated screenshots to vision models and parses structured
action responses. Supports grid-based targeting where the model
references cell labels (e.g., "B3") instead of raw pixel coordinates.

Provider is Gemini by default. Additional providers can be added
by implementing a _analyze_{provider} function and adding an elif
in analyze_screenshot().

Requires GEMINI_API_KEY or GOOGLE_API_KEY environment variable.
"""

import io
import json
import logging
import os
from dataclasses import dataclass

from PIL import Image

from assistant.screen import overlay_grid

logger = logging.getLogger(__name__)

# Actions the model can request — must match input module vocabulary + "done"
VALID_ACTIONS = frozenset(
    {
        "left_click",
        "right_click",
        "double_click",
        "type",
        "key",
        "mouse_move",
        "scroll",
        "done",
    }
)

GRID_ANALYSIS_PROMPT = """You are a computer control agent. Analyze this screenshot which has a \
{cols}x{rows} grid overlay (columns A-{max_col}, rows 1-{max_row}).

Current task: {task}

{history_section}

Respond with EXACTLY this JSON format:
{{
    "reasoning": "Brief analysis of what you see and your plan",
    "action": "left_click|right_click|double_click|type|key|scroll|done",
    "target": "B3",
    "text": null,
    "confidence": "high|medium|low"
}}

Rules:
- For click actions: set "target" to a grid cell, "text" to null
- For type actions: set "text" to the text to type, "target" to the cell to click first (or null \
if already focused)
- For key actions: set "text" to the key combo (e.g., "ctrl+s", "enter"), "target" to null
- For scroll actions: set "target" to the cell to scroll at, "text" to "up" or "down"
- For done: set when the task appears complete, "target" and "text" to null
- Only output the JSON object, no other text"""


@dataclass(frozen=True)
class VisionResponse:
    """Structured response from a vision model analysis."""

    reasoning: str
    action: str
    target: str | None
    text: str | None
    confidence: str


def analyze_screenshot(
    image: Image.Image,
    task: str,
    history: list[dict] | None = None,
    provider: str = "gemini",
    grid_cols: int = 10,
    grid_rows: int = 8,
) -> VisionResponse:
    """Send a screenshot to a vision model and get a structured action response.

    The image is annotated with a grid overlay before sending. The model
    responds with an action referencing grid cells.

    Args:
        image: Raw screenshot (grid overlay is applied internally).
        task: Natural language description of what to accomplish.
        history: Previous steps for context (list of dicts with
            "action", "target", "reasoning" keys).
        provider: Vision model provider ("gemini").
        grid_cols: Grid columns for overlay.
        grid_rows: Grid rows for overlay.

    Returns:
        VisionResponse with the model's action decision.
    """
    annotated = overlay_grid(image, cols=grid_cols, rows=grid_rows)

    # Build the prompt with grid dimensions and history
    max_col = chr(64 + grid_cols)
    history_section = _format_history(history) if history else "No previous actions."

    prompt = GRID_ANALYSIS_PROMPT.format(
        cols=grid_cols,
        rows=grid_rows,
        max_col=max_col,
        max_row=grid_rows,
        task=task,
        history_section=history_section,
    )

    # Convert image to bytes for the provider
    image_bytes = _image_to_bytes(annotated)

    if provider == "gemini":
        return _analyze_gemini(image_bytes, prompt)

    raise ValueError(f"Unknown vision provider: {provider!r}. Available: gemini")


def _format_history(history: list[dict]) -> str:
    """Format recent action history for the prompt."""
    lines = ["Previous actions:"]
    for i, step in enumerate(history):
        action = step.get("action", "?")
        target = step.get("target", "")
        reasoning = step.get("reasoning", "")
        lines.append(f"  Step {i + 1}: {action} {target} — {reasoning}")
    return "\n".join(lines)


def _image_to_bytes(image: Image.Image) -> bytes:
    """Convert a PIL Image to PNG bytes."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _parse_response(raw_text: str) -> VisionResponse:
    """Parse JSON from model output into a VisionResponse.

    Handles markdown code fences and whitespace. Returns an error
    response if parsing fails — the agent loop decides what to do.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse vision model response: %s", text[:200])
        return VisionResponse(
            reasoning=f"Parse error. Raw response: {text[:500]}",
            action="error",
            target=None,
            text=None,
            confidence="low",
        )

    action = data.get("action", "error")
    if action not in VALID_ACTIONS:
        logger.warning("Unknown action from model: %s", action)
        action = "error"

    return VisionResponse(
        reasoning=data.get("reasoning", ""),
        action=action,
        target=data.get("target"),
        text=data.get("text"),
        confidence=data.get("confidence", "medium"),
    )


def _get_api_key() -> str:
    """Get the Gemini API key from environment variables."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError(
            "No API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
        )
    return key


def _analyze_gemini(image_bytes: bytes, prompt: str) -> VisionResponse:
    """Send image + prompt to Gemini and parse the response."""
    from google import genai

    api_key = _get_api_key()
    client = genai.Client(api_key=api_key)

    # Send image as inline data with the prompt
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            genai.types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            prompt,
        ],
    )

    raw_text = response.text
    logger.debug("Gemini response: %s", raw_text[:200])
    return _parse_response(raw_text)
