"""Interactive demo of the vision module.

Run with Ollama:  uv run python scripts/demo_agent_interactive.py
Run with Gemini:  uv run python scripts/demo_agent_interactive.py --provider gemini

Captures screen, sends to model with a task, displays the response,
and loops until the user types 'quit'.
"""

import argparse

from assistant.screen import capture_screen, overlay_grid, save_capture
from assistant.vision import analyze_screenshot


def parse_args():
    parser = argparse.ArgumentParser(description="Interactive agent demo")
    parser.add_argument("--provider", default="ollama", help="Vision provider (default: ollama)")
    parser.add_argument("--model", default=None, help="Model name (default: provider default)")
    parser.add_argument("--monitor", type=int, default=1, help="Monitor index")
    parser.add_argument("--cols", type=int, default=10, help="Grid columns")
    parser.add_argument("--rows", type=int, default=8, help="Grid rows")
    parser.add_argument("--save-grid", action="store_true", help="Save annotated screenshots")
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"Provider: {args.provider}")
    print(f"Model: {args.model or '(default)'}")
    print(f"Monitor: {args.monitor}")
    print(f"Grid: {args.cols}x{args.rows}")
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

        print(f"\n  Reasoning:   {response.reasoning}")
        print(f"  Action:      {response.action}")
        print(f"  Target:      {response.target}")
        print(f"  Text:        {response.text}")
        print(f"  Confidence:  {response.confidence}")
        print()


if __name__ == "__main__":
    main()
