# Assistant

A Python-based computer control agent. Takes screenshots, reasons about what's on screen using vision models, and executes actions (click, type, navigate) to accomplish tasks on your behalf.

## How It Works

The agent operates in a **capture → reason → act** loop:

1. Capture a screenshot and overlay a labeled grid
2. Send the annotated image to a vision model (via OpenRouter or local Ollama)
3. Model responds with a structured JSON action referencing grid cells (e.g., `left_click B3`)
4. Execute the action, capture the new state, repeat

Grid-based targeting is model-agnostic, token-efficient, and more precise than raw coordinate prediction.

## Library Modules (`src/assistant/`)

| Module | Purpose |
|--------|---------|
| `screen` | Screenshot capture (mss), monitor listing, grid overlay, grid-to-pixel conversion |
| `input` | Mouse and keyboard control (PyAutoGUI) with action dispatcher |
| `vision` | Vision model integration — sends annotated screenshots, parses structured responses |
| `agent` | Agent loop: capture → reason → act → verify. Session logging as JSONL |
| `config` | Centralized model defaults and provider settings |
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

# Agent loop
assistant run "open Safari and search for weather"  # full autonomous loop
assistant run "close this dialog" --dry-run          # analyze without acting
assistant run "fill in the form" --provider ollama   # use local model

assistant --version
```

## Project Structure

```
src/assistant/       # Reusable library — screen capture, input, vision, agent loop
automations/         # Personal automation scripts built on the library (see automations/README.md)
tests/               # Mirrors src/ structure
docs/                # Conventions, brainstorming
```

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 1 | Screen capture (mss + PIL) | Done |
| 2 | CLI (typer) | Done |
| 3 | Input, vision, and agent loop | Done |
| 4 | Claude Code skills | Planned |
| 5 | Memory / RAG (SQLite FTS5) | Planned |

See [docs/BRAINSTORMING.md](docs/BRAINSTORMING.md) for architecture decisions and feature vision.

## Development

Requires Python 3.12+. Uses [uv](https://docs.astral.sh/uv/) for package management.

```bash
uv pip install -e ".[dev]"        # install
uv run ruff check . && uv run ruff format .  # lint + format
uv run pytest                      # test
```

See [docs/CONVENTIONS.md](docs/CONVENTIONS.md) for the full workflow guide (git, commits, testing, style).
