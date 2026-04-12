# Automations

Personal automation scripts built on the [assistant library](../src/assistant/). Each automation is a self-contained project that imports from the library but never modifies it.

## Projects

| Directory | CLI Entry Point | Description |
|-----------|----------------|-------------|
| [`ln_voice_over/`](ln_voice_over/) | `lnvo` | Light novel text-to-audiobook pipeline with per-character voice synthesis |

## Adding an Automation

1. Create a new directory under `automations/`.
2. Add a `README.md` explaining what it does and how to use it.
3. If it needs a CLI, register the entry point in `pyproject.toml` under `[project.scripts]`.
4. Import from `assistant.*` for screen capture, input, vision, etc. Never modify the library.
