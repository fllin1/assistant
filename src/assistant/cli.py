"""CLI interface for the assistant library.

Wraps screen capture and input control in a typer-based CLI.
Entry point configured in pyproject.toml as 'assistant'.
"""

from typing import Annotated

import typer

from assistant.config import DEFAULT_MONITOR

app = typer.Typer(help="Local screen capture and input control helpers.")


def _version_callback(value: bool) -> None:
    if value:
        from assistant import __version__

        typer.echo(f"assistant {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """Local screen capture and input control helpers."""


@app.command()
def capture(
    monitor: int = typer.Option(
        DEFAULT_MONITOR,
        help="Monitor index (0=all, 1=primary, 2+=additional).",
    ),
    label: str = typer.Option("full", help="Label for the saved file."),
    grid: bool = typer.Option(False, help="Overlay a labeled grid on the screenshot."),
    cols: int = typer.Option(10, help="Grid columns (only with --grid)."),
    rows: int = typer.Option(8, help="Grid rows (only with --grid)."),
    output: str | None = typer.Option(None, help="Output directory override."),
) -> None:
    """Capture a screenshot and save it."""
    from pathlib import Path

    from assistant.screen import capture_screen, overlay_grid, save_capture

    img = capture_screen(monitor=monitor)

    if grid:
        img = overlay_grid(img, cols=cols, rows=rows)
        label = f"{label}_grid_{cols}x{rows}"

    directory = Path(output) if output else None
    path = save_capture(img, label=label, directory=directory)
    typer.echo(f"Saved: {path}")


@app.command()
def monitors() -> None:
    """List available monitors and their geometry."""
    from assistant.screen import list_monitors

    for i, m in enumerate(list_monitors()):
        tag = "combined" if i == 0 else f"monitor {i}"
        typer.echo(f"  [{i}] {tag}: {m['width']}x{m['height']} at ({m['left']},{m['top']})")


@app.command()
def click(
    target: str = typer.Argument(help="Grid cell (e.g., B3) or pixel coords (e.g., 500,300)."),
    monitor: int = typer.Option(
        DEFAULT_MONITOR,
        help="Monitor for grid resolution (ignored for pixel coords).",
    ),
    right: bool = typer.Option(False, help="Right-click instead of left-click."),
    double: bool = typer.Option(False, help="Double-click."),
) -> None:
    """Click at a grid cell or pixel coordinate."""
    from assistant.input import double_click, left_click, right_click

    x, y = _resolve_target(target, monitor)

    if double:
        double_click(x, y)
    elif right:
        right_click(x, y)
    else:
        left_click(x, y)
    typer.echo(f"Clicked ({x}, {y})")


@app.command(name="type")
def type_cmd(
    text: str = typer.Argument(help="Text to type at the current cursor position."),
) -> None:
    """Type text at the current cursor position."""
    from assistant.input import type_text

    type_text(text)
    typer.echo(f"Typed: {text!r}")


@app.command()
def key(
    combo: str = typer.Argument(help="Key or combo (e.g., 'enter', 'ctrl+s')."),
) -> None:
    """Press a key or key combination."""
    from assistant.input import press_key

    press_key(combo)
    typer.echo(f"Pressed: {combo}")


def _resolve_target(target: str, monitor: int) -> tuple[int, int]:
    """Parse a target string as either pixel coords (500,300) or grid cell (B3)."""
    if "," in target:
        parts = target.split(",")
        return int(parts[0].strip()), int(parts[1].strip())

    # Grid cell reference — need screen dimensions to resolve
    from assistant.screen import capture_screen, grid_to_screen_pixel

    img = capture_screen(monitor=monitor)
    return grid_to_screen_pixel(target, monitor=monitor, image_size=img.size)
