# Assistant

A Python-based computer control agent. Takes screenshots, reasons about what's on screen using vision models, and executes actions (click, type, navigate) to accomplish tasks on your behalf.

## How It Works

The agent operates in a **capture → reason → act** loop:

1. Capture a screenshot and overlay a labeled grid
2. Send the annotated image to a vision model (Claude, Gemini)
3. Model responds with a grid reference (e.g., "click B3") instead of guessing pixel coordinates
4. Execute the action, capture the new state, repeat

Grid-based targeting is model-agnostic, token-efficient, and more precise than raw coordinate prediction. For dense UIs, adaptive zoom refines to sub-cell precision.

## Project Structure

```
src/assistant/       # Reusable library — screen capture, input, vision, agent loop
automations/         # Personal automation scripts built on the library
tests/               # Mirrors src/ structure
docs/                # Conventions, structure map, brainstorming
```

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 1 | Screen capture (mss + PIL) | Next |
| 2 | CLI (typer) | Planned |
| 3 | AI screen interaction (input + vision + agent loop) | Planned |
| 4 | Claude Code skills | Planned |
| 5 | Memory / RAG (SQLite FTS5) | Planned |

See [docs/BRAINSTORMING.md](docs/BRAINSTORMING.md) for architecture decisions and feature vision.

## Development

Requires Python 3.12+. Uses [uv](https://docs.astral.sh/uv/) for package management.

```bash
uv pip install -e ".[dev]"    # install
ruff check . && ruff format . # lint + format
pytest                         # test
```

See [docs/CONVENTIONS.md](docs/CONVENTIONS.md) for the full workflow guide (git, commits, testing, style).
