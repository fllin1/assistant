# Assistant

A Python package for local screen capture and input control. The experimental prototype
has been removed so the next design can start from a clean base.

## How It Works

The current package exposes simple local primitives:

1. Capture a screenshot or monitor geometry
2. Optionally overlay a labeled grid
3. Convert grid cells to absolute screen coordinates
4. Execute explicit mouse and keyboard actions

## Library Modules (`src/assistant/`)

| Module | Purpose |
|--------|---------|
| `screen` | Screenshot capture (mss), monitor listing, grid overlay, grid-to-pixel conversion |
| `input` | Mouse and keyboard control (PyAutoGUI) with action dispatcher |
| `config` | Centralized package defaults |
| `cli` | Typer CLI wrapping all modules into user-facing commands |

## CLI Usage

```bash
# Screen capture
assistant capture                # screenshot of primary monitor
assistant capture --grid         # with labeled grid overlay
assistant capture --monitor 0    # all monitors combined
assistant monitors               # list available monitors

# Input control
assistant click B3               # click a grid cell
assistant click 500,300          # click pixel coordinates
assistant type "hello world"     # type text at cursor
assistant key "ctrl+s"           # press a key combo

assistant --version
```

## Project Structure

```
src/assistant/       # Reusable library: screen capture, monitor geometry, input control
automations/         # Personal automation scripts built on the library (see automations/README.md)
tests/               # Grouped tests for assistant, automations, and scripts
docs/                # Conventions and generated architecture notes
```

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 1 | Screen capture (mss + PIL) | Done |
| 2 | CLI (typer) | Done |
| 3 | Input control | Done |
| 4 | Future interaction research | Parked for separate repo |

## Development

Requires Python 3.12+. Uses [uv](https://docs.astral.sh/uv/) for package management.

```bash
uv pip install -e ".[dev]"        # install
uv run ruff check . && uv run ruff format .  # lint + format
uv run pytest                      # all non-live tests
uv run pytest tests/assistant      # core assistant package tests
uv run pytest tests/automations    # automation project tests
```

See [docs/CONVENTIONS.md](docs/CONVENTIONS.md) for the full workflow guide (git, commits, testing, style).
