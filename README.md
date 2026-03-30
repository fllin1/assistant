# Assistant

A computer control agent that uses vision models to understand your screen and take actions on your behalf — clicking, typing, navigating web pages, and more.

## Project Status

**Early development** — project scaffolding is in place, no features implemented yet.

## Architecture

The project is split into two layers:

- **`src/assistant/`** — A reusable Python library providing building blocks for computer control (screen capture, input simulation, browser automation, vision model integration).
- **`automations/`** — Personal automation scripts that use the library for specific tasks.

## Development

Requires Python 3.12+. Uses [uv](https://docs.astral.sh/uv/) for package management.

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run linter and formatter
ruff check .
ruff format .

# Run tests
pytest
```

## Tooling

| Tool | Purpose |
|------|---------|
| **Ruff** | Linting + formatting |
| **pytest** | Testing |
| **Conventional Commits** | Commit message format |
| **GitHub Flow** | Branching model |
