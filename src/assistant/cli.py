"""CLI interface for the assistant library.

Wraps the screen capture module (and future modules) in a typer-based CLI.
Entry point configured in pyproject.toml as 'assistant'.
"""

import logging
from typing import Annotated

import typer

app = typer.Typer(help="Computer control agent with vision-based screen understanding.")
logger = logging.getLogger(__name__)


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
    """Computer control agent with vision-based screen understanding."""


@app.command()
def capture(
    monitor: int = typer.Option(1, help="Monitor index (0=all, 1=primary, 2+=additional)."),
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
