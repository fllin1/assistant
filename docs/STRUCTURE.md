# Codebase Structure

> This document is kept up-to-date whenever the project structure changes.
> Last updated: 2026-04-04

## Directory Layout

```
assistant/
├── main.py                          # Entry point
├── pyproject.toml                   # Project config, dependencies, ruff & pytest settings
├── CLAUDE.md                        # Claude rules for this project
├── docs/
│   ├── BRAINSTORMING.md              # Architecture decisions, feature vision, open questions
│   ├── CONVENTIONS.md               # How we work — style, git, testing, deps
│   └── STRUCTURE.md                 # This file — living codebase map
├── scripts/
│   └── ruff_hook.sh                 # PostToolUse hook — runs ruff on .py edits
├── src/
│   └── assistant/                   # Reusable library (flat, grows organically)
│       ├── __init__.py
│       └── screen.py                # Screen capture (mss), grid overlay
├── automations/                     # Personal automation scripts (import from library)
│   └── __init__.py
└── tests/
    ├── __init__.py
    └── test_screen.py               # Tests for screen capture module
```

## Module Responsibilities

### `src/assistant/`
Reusable library for computer control. Starts flat — modules are added as features are built.

**Implemented:**
- `screen.py` — Screen capture via mss, save with auto-naming, grid overlay for model targeting

**Planned:**
- Input control (mouse/keyboard)
- Vision model integration
- Agent loop orchestration

### `automations/`
Personal automation scripts built on top of the library. Each script or module is self-contained and imports from `assistant`.

### `tests/`
Mirrors the `src/` structure. Test files named `test_<module>.py`.

### `scripts/`
Developer tooling — hooks, helpers, CI scripts. Not part of the library.
