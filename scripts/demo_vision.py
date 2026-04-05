"""Visual demo of the vision module.

Run: GEMINI_API_KEY=your-key uv run python scripts/demo_vision.py

Captures the screen, sends it to Gemini with a sample task,
and prints the structured response.
"""

from assistant.screen import capture_screen
from assistant.vision import analyze_screenshot


def main():
    print("Capturing screen...")
    img = capture_screen(monitor=1)
    print(f"  Screenshot: {img.size[0]}x{img.size[1]}")

    task = "Describe what you see on the screen. Respond with action 'done'."
    print(f"  Task: {task}")
    print("  Sending to Gemini...")

    response = analyze_screenshot(img, task=task)

    print(f"\n  Action: {response.action}")
    print(f"  Target: {response.target}")
    print(f"  Text: {response.text}")
    print(f"  Confidence: {response.confidence}")
    print(f"  Reasoning: {response.reasoning}")


if __name__ == "__main__":
    main()
