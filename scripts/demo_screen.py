"""Visual demo of the screen capture module.

Run: uv run python scripts/demo_screen.py

Captures the screen and saves grid overlay variants for visual inspection.
Output goes to ~/.assistant/captures/{date}/.
"""

from assistant.screen import capture_screen, overlay_grid, save_capture


def main():
    img = capture_screen(monitor=1)
    save_capture(img, label="raw")

    for cols, rows in [(5, 4), (10, 8), (20, 15)]:
        grid = overlay_grid(img, cols=cols, rows=rows)
        save_capture(grid, label=f"grid_{cols}x{rows}")
        print(f"  Saved grid {cols}x{rows}")

    print(f"\nCapture size: {img.size[0]}x{img.size[1]}")
    print("Output: ~/.assistant/captures/")


if __name__ == "__main__":
    main()
