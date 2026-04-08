"""Vision model integration for screen analysis.

Sends annotated screenshots to vision models and parses structured
action responses. Supports grid-based targeting where the model
references cell labels (e.g., "B3") instead of raw pixel coordinates.

Supported providers:
- "openrouter": OpenAI-compatible API via OpenRouter (requires OPENROUTER_API_KEY env var).
    Supports 200+ models including Gemini, Claude, Llama, etc.
- "ollama": Local Ollama instance (requires Ollama running, configurable via OLLAMA_HOST)
"""

import base64
import io
import json
import logging
import os
from dataclasses import dataclass

from openai import OpenAI
from PIL import Image

from assistant.config import DEFAULT_MODELS, DEFAULT_OLLAMA_HOST
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
    provider: str = "openrouter",
    model: str | None = None,
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
        provider: Vision model provider ("openrouter" or "ollama").
        model: Model name override. Defaults to provider-specific default.
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

    image_bytes = _image_to_bytes(annotated)

    resolved_model = model or DEFAULT_MODELS.get(provider)

    if provider == "openrouter":
        return _analyze_openrouter(image_bytes, prompt, model=resolved_model)
    elif provider == "ollama":
        return _analyze_ollama(image_bytes, prompt, model=resolved_model)

    raise ValueError(f"Unknown vision provider: {provider!r}. Available: openrouter, ollama")


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


def _analyze_openrouter(
    image_bytes: bytes, prompt: str, model: str = DEFAULT_MODELS["openrouter"]
) -> VisionResponse:
    """Send image + prompt via OpenRouter (OpenAI-compatible API).

    Requires OPENROUTER_API_KEY environment variable.
    Supports any vision model available on OpenRouter.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("No API key found. Set OPENROUTER_API_KEY environment variable.")

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ],
    )

    raw_text = response.choices[0].message.content
    if raw_text is None:
        raise ValueError(f"OpenRouter ({model}): No response")

    logger.debug("OpenRouter response (%s): %s", model, raw_text[:200])
    return _parse_response(raw_text)


def _analyze_ollama(
    image_bytes: bytes, prompt: str, model: str = DEFAULT_MODELS["ollama"]
) -> VisionResponse:
    """Send image + prompt to a local Ollama instance and parse the response.

    Uses the official ollama Python package. Ollama must be running.
    Configure host via OLLAMA_HOST env var (default: http://localhost:11434).
    """
    from ollama import chat

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    try:
        response = chat(
            model=model,
            messages=[{"role": "user", "content": prompt, "images": [image_b64]}],
        )
    except Exception as e:
        if "connect" in str(e).lower():
            host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
            raise ConnectionError(
                f"Cannot connect to Ollama at {host}. "
                "Is Ollama running? Start it with: ollama serve"
            ) from e
        raise

    raw_text = response["message"]["content"]
    logger.debug("Ollama response (%s): %s", model, raw_text[:200])
    return _parse_response(raw_text)
