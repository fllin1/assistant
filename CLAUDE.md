# Assistant Project - Claude Conductor Rules

Claude Code is the conductor for larger project work. Codex agents are the
implementers.

## First Reads

1. Read `AGENTS.md` for repo-wide engineering, testing, branch, and commit
   rules.
2. Read the relevant package `AGENTS.md` and `CONTEXT.md` before planning work
   inside a sub-project.
3. Read `docs/lnvo/` when the task touches LNVO vocabulary, pipeline contracts,
   or cross-project planning.

## Project Map

| Area                 | Role                                                      |
| -------------------- | --------------------------------------------------------- |
| `src/assistant/`     | reusable library code.                                    |
| `automations/`       | self-contained personal automations.                      |
| `docs/lnvo/`         | repo-tracked LNVO reference docs, viewable from Obsidian. |
| package `CONTEXT.md` | local vocabulary and execution context for one package.   |

Automation sub-projects are self-contained. Apply only the relevant
`AGENTS.md` / `CLAUDE.md` files and the files they explicitly name. Ignore
conventions from sibling automations or unrelated repo docs.

Use standard branch names for delegated work: `feat/short-description` for
features and `fix/short-description` for fixes. Do not create branches named
after Codex, Claude, or any other agent/tool.

## Claude Responsibilities

- clarify goals, scope, acceptance criteria, and review gates;
- choose the execution sequence;
- split implementation into bounded Codex-agent tasks;
- preserve consistency across docs, contracts, code, and tests;
- integrate agent results before presenting completion;
- surface unresolved decisions instead of hiding contract changes.

## Delegation Protocol

Each Codex-agent task should include:

- objective;
- allowed files or module scope;
- input contracts or reference docs;
- expected output;
- verification command;
- stop condition.

## Contract Changes

Public contract changes update the full reference set:

- `docs/lnvo/` reference page;
- Pydantic contract model;
- validator or round-trip tests;
- package `CONTEXT.md` only when local vocabulary changes.

Do not silently change public stage names, artifact paths, enum values, or
required keys.

## Documentation Model

`docs/lnvo/` is the canonical Markdown source for LNVO reference material.

README files are user-facing entry points. `CONTEXT.md` files are agent-facing
local context.

## Completion Output

When reporting completed work, include:

- result;
- agents or slices used;
- files changed;
- verification evidence;
- review checklist;
- unresolved risks or decisions.

Do not commit unless the user explicitly asks Claude Code to commit.
