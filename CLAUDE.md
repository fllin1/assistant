# Assistant Project — Claude Rules

## Project Overview

A Python-based computer control agent. The project has two layers:
- **Library** (`src/assistant/`): reusable building blocks for computer control, usable by anyone
- **Automations** (`automations/`): personal scripts that import from the library for specific use cases

The library starts flat — modules are added as we build them. Structure emerges from usage, not speculation.

## Workflow Rules

### Scope Control
- **One module/feature per edit session.** Never touch unrelated modules in the same session.
- Each agent (subagent) must limit its edits to a single module or feature.
- If a change requires touching multiple modules, discuss the plan first and proceed module by module.

### Commit Discipline
- **Pause and commit after tests pass.** Do not continue to the next feature without committing.
- Use **Conventional Commits**: `feat(module):`, `fix(module):`, `refactor(module):`, `docs:`, `test:`, `chore:`.
- Commit messages should explain *why*, not just *what*.
- Remind the user to commit if they haven't after completing a feature.

### Branch Management (GitHub Flow)
- `main` is always deployable.
- Create a feature branch for each new feature: `feat/short-description`.
- Fix branches: `fix/short-description`.
- Remind the user to merge completed feature branches back to main.
- Remind the user to delete merged branches.

### Documentation
- Every module must have a module-level docstring explaining its purpose.
- Public functions use **Google-style docstrings** — skip docstrings for trivial/self-explanatory functions.

## Code Style

### Formatting & Linting
- **Ruff** is the single tool for formatting and linting. Run `ruff check .` and `ruff format .`.
- If handwritten code by the user does not pass ruff, notify them.

### Type Hints
- **Pragmatic**: type all public function signatures and complex internal functions.
- Skip type hints for trivial local variables and obvious cases.

### Error Handling
- **No `try/except` unless genuinely necessary** (e.g., external I/O, network calls, user input).
- Never use bare `except:` or `except Exception:` as a catch-all.
- Let errors propagate naturally — don't swallow them.

### Code Comments
- Write brief comments on non-trivial blocks explaining **what** the block does and **why** this approach was chosen.
- Target audience: the user and future AI assistants reading the code.
- Key things to call out: design trade-offs, platform-specific behavior, non-obvious constraints, and links to related modules.
- Do NOT comment obvious code. `# increment counter` above `counter += 1` is noise.

### General
- No unnecessary abstractions. Three similar lines > premature abstraction.
- No speculative features or "just in case" code.
- Imports: stdlib first, then third-party, then local. Ruff handles ordering.

## Testing
- **pytest** is the testing framework.
- Tests live in `tests/` mirroring the `src/` structure.
- Test file naming: `test_<module>.py`.
- Run `pytest` before committing. Do not commit if tests fail.

## Two-Tier Rules

### Library (`src/assistant/`)
- Changes require careful review and discussion.
- Must maintain backward compatibility with existing automations.
- Must have tests before merging.
- Public APIs must be typed and documented.

### Automations (`automations/`)
- Greater autonomy allowed — a well-written planning prompt should be sufficient to generate an automation.
- Each automation is a self-contained script or module.
- Automations import from the library but never modify it.
- Automations should include a docstring explaining what they do and how to use them.

## Documentation Maintenance
- The root `README.md` describes the **library** (`src/assistant/`): its modules, CLI commands, and roadmap. It should not document automations — those have their own READMEs.
- When library modules, CLI commands, or the roadmap change, update the root `README.md` to match.
- Each automation under `automations/` should have its own `README.md` documenting its purpose and CLI usage.

## Reminders for Claude
- Always read a file before editing it.
- Notify the user if their code doesn't match the style guidelines.
- After completing a feature: remind to commit.
- After completing a feature or set of changes: **provide a review plan** — a step-by-step checklist for the user to code-review and hand-test the changes. Include: files to read in order, test commands, manual verification steps, and edge cases to try.
- Before starting work: check which branch we're on and whether it's the right one.
- Every feature in `src/assistant/` must be linked to a GitHub Issue. If no issue exists, create one before starting work. Work on the branch that matches the feature scope — don't add unrelated features to an existing branch. Changes scoped to `automations/` do **not** require an issue.
- When in doubt about scope, ask — don't expand silently.
- Do not commit unless the user explicitly tells you to.
