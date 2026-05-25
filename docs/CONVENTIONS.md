# Conventions & Workflow Guide

> How we work on this project. Read this before contributing.

## Code Style

**Ruff** handles formatting and linting. No other tools needed.

```bash
ruff check .       # lint
ruff format .      # format
```

### Naming

| Thing | Convention | Example |
|-------|-----------|---------|
| Files | `snake_case.py` | `screen.py`, `input.py` |
| Functions | `snake_case` | `capture_screen()` |
| Classes | `PascalCase` | `ScreenRegion` |
| Constants | `UPPER_SNAKE` | `DEFAULT_MONITOR` |
| Test files | `test_<module>.py` | `test_screen.py` |
| Test functions | `test_<function>_<scenario>` | `test_capture_screen_returns_rgb` |

### Type Hints

Type all public function signatures and complex internal functions. Skip trivial local variables.

### Docstrings

Google style. Only on non-trivial functions — skip obvious getters/setters.

### Error Handling

No `try/except` unless genuinely necessary (external I/O, network, user input). Never bare `except:` or `except Exception:`.

### Imports

stdlib, then third-party, then local. Ruff enforces ordering.

## Testing

- Framework: **pytest**
- Tests live in `tests/`, grouped by project surface: `tests/assistant/`,
  `tests/automations/`, and `tests/scripts/`
- Hardware-dependent tests: mark with `@pytest.mark.live`, skipped in CI
- File output tests: use pytest's `tmp_path` fixture — auto-cleaned, outside repo

```bash
pytest tests/assistant     # run core assistant package tests
pytest tests/automations   # run automation project tests
pytest tests/scripts       # run script/tooling tests
pytest                     # run all non-live tests
pytest -m live             # run only live/hardware tests
```

## Git Workflow (GitHub Flow)

### Branches

`main` is always deployable. Branch for every feature or fix.

| Branch type | Naming | Example |
|-------------|--------|---------|
| Feature | `feat/short-description` | `feat/screen-capture` |
| Fix | `fix/short-description` | `fix/region-offset` |

One feature per branch. Keep branches focused and short-lived.

### Commits (Conventional Commits)

Format: `type(scope): description`

| Type | When |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change, no behavior change |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `chore` | Tooling, config, dependencies |

Message explains **why**, not what. Commit after tests pass, before starting the next feature.

### Pull Requests

1. Push branch, open PR against `main`
2. PR title matches the main commit message
3. Description: what changed, why, how to test
4. All tests must pass
5. Squash merge for clean history
6. Delete the branch after merge

### Linking to Issues

Reference issues in commits and PRs:

- `feat(screen): add capture_window (fixes #3)` — auto-closes issue #3 on merge
- `relates to #5` — links without closing

## Dependencies

- Package manager: **uv** (never raw pip)
- Minimal dependencies — stdlib first, one tool per job
- Pin minimum versions: `"mss>=9.0"`, not exact pins

```bash
uv add mss                 # add a dependency
uv pip install -e ".[dev]" # install project in dev mode
```

## Runtime Data

All runtime data lives in `~/.assistant/` — **outside the repo**. Nothing generated at runtime should ever be inside the project directory.

| Directory | Purpose |
|-----------|---------|
| `~/.assistant/captures/` | Saved screenshots |

Captures use date-partitioned directories with timestamp naming:

```
~/.assistant/captures/2026-04-01/143052_full.png
```

## Cross-Platform

Linux (WSL2) is the primary development platform. Windows is supported.

Platform-specific code is isolated to dedicated functions — never scattered through business logic.

## Backlog Tracking

Use **GitHub Issues** for features, bugs, and TODOs.

- Label issues: `feat`, `fix`, `refactor`, `question`
- Put the module name in the title when relevant (e.g. `feat: screen — capture_window()`)
- Link issues to branches, commits, and PRs
