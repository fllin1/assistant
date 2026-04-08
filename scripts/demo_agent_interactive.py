"""Interactive demo of the vision module.

Run with Ollama:  uv run python scripts/demo_agent_interactive.py
Run with Gemini:  uv run python scripts/demo_agent_interactive.py --provider gemini
Stream output:    uv run python scripts/demo_agent_interactive.py --stream

Captures screen, sends to model with a task, displays the response,
and loops until the user types 'quit'.
"""

import argparse
import base64

from assistant.config import DEFAULT_MODELS
from assistant.screen import capture_screen, overlay_grid, save_capture
from assistant.vision import (
    GRID_ANALYSIS_PROMPT,
    _image_to_bytes,
    _parse_response,
    analyze_screenshot,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Interactive agent demo")
    parser.add_argument("--provider", default="ollama", help="Vision provider (default: ollama)")
    parser.add_argument("--model", default=None, help="Model name (default: provider default)")
    parser.add_argument("--monitor", type=int, default=1, help="Monitor index")
    parser.add_argument("--cols", type=int, default=10, help="Grid columns")
    parser.add_argument("--rows", type=int, default=8, help="Grid rows")
    parser.add_argument("--save-grid", action="store_true", help="Save annotated screenshots")
    parser.add_argument("--stream", action="store_true", help="Stream model output token by token")
    parser.add_argument("--verbose", action="store_true", help="Show debug logs from all modules")
    return parser.parse_args()


def _stream_ollama(image_bytes, prompt, model):
    """Call Ollama with streaming via the official package. Tokens print as they arrive."""
    from ollama import chat

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    full_response = ""
    print("\n--- Model output ---")
    try:
        stream = chat(
            model=model,
            messages=[{"role": "user", "content": prompt, "images": [image_b64]}],
            stream=True,
        )
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                print(token, end="", flush=True)
                full_response += token
    except Exception as e:
        if "connect" in str(e).lower():
            print("\n  ERROR: Cannot connect to Ollama. Is it running?")
            return None
        raise

    print("\n--- End output ---\n")
    return _parse_response(full_response)


def main():
    import logging

    args = parse_args()

    if args.verbose:
        # Only enable debug for our modules — not httpx/openai which log full HTTP payloads
        logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
        logging.getLogger("assistant").setLevel(logging.DEBUG)

    model = args.model or DEFAULT_MODELS.get(args.provider, "unknown")
    print(f"Provider: {args.provider}")
    print(f"Model: {model}")
    print(f"Monitor: {args.monitor}")
    print(f"Grid: {args.cols}x{args.rows}")
    if args.stream:
        print("Streaming: ON")
    print("Type a task and press Enter. Type 'quit' to exit.\n")

    while True:
        try:
            task = input("Task> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not task or task.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        print("Capturing screen...")
        img = capture_screen(monitor=args.monitor)

        if args.save_grid:
            grid_img = overlay_grid(img, cols=args.cols, rows=args.rows)
            path = save_capture(grid_img, label="interactive_grid")
            print(f"  Grid saved: {path}")

        print(f"Sending to {args.provider}...")

        # Streaming mode: use ollama package with stream=True
        if args.stream and args.provider == "ollama":
            annotated = overlay_grid(img, cols=args.cols, rows=args.rows)
            image_bytes = _image_to_bytes(annotated)

            max_col = chr(64 + args.cols)
            prompt = GRID_ANALYSIS_PROMPT.format(
                cols=args.cols,
                rows=args.rows,
                max_col=max_col,
                max_row=args.rows,
                task=task,
                history_section="No previous actions.",
            )

            response = _stream_ollama(image_bytes, prompt, model)
            if response is None:
                continue
        else:
            try:
                response = analyze_screenshot(
                    img,
                    task=task,
                    provider=args.provider,
                    model=args.model,
                    grid_cols=args.cols,
                    grid_rows=args.rows,
                )
            except ConnectionError as e:
                print(f"  ERROR: {e}")
                continue
            except ValueError as e:
                print(f"  ERROR: {e}")
                continue

        print(f"  Reasoning:   {response.reasoning}")
        print(f"  Action:      {response.action}")
        print(f"  Target:      {response.target}")
        print(f"  Text:        {response.text}")
        print(f"  Confidence:  {response.confidence}")
        print()


if __name__ == "__main__":
    main()
