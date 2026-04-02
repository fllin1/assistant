# Brainstorming & Feature Vision

> Living document capturing architecture decisions, feature ideas, and open questions.
> Not a TODO list — use GitHub Issues for trackable work items.

## Architecture Decisions

### Core Pattern: Capture → Reason → Act

The agent operates in a loop:
1. **Capture** — take a screenshot of the current screen state
2. **Reason** — send to a vision model, get back a structured decision
3. **Act** — execute the decision (click, type, navigate, etc.)
4. **Repeat** — capture new state, verify outcome

Each iteration produces a **frozen snapshot** (immutable dataclass) — a record of what was seen, what was decided, and what was done. These snapshots form an inspectable history that can never be mutated after creation.

### Bounded Execution

The agent loop must have explicit bounds:
- **Max iterations** — prevent infinite loops
- **Timeout** — wall-clock limit per session
- **Stop conditions** — explicit signals to halt (goal reached, error, user interrupt)

Even automations should be bounded. "Run forever" is never the default.

### Tool Registry

Modules (screen, input, browser, vision) shouldn't just be importable functions — they should register as **tools** with metadata. This lets the vision model know what actions are available when reasoning.

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    execute: Callable

# Example: the screen module registers its capabilities
SCREEN_TOOLS = [
    Tool(
        name="capture_screen",
        description="Take a screenshot of the full screen or a specific monitor",
        execute=capture_screen,
    ),
    Tool(
        name="capture_region",
        description="Capture a rectangular region of the screen at specific coordinates",
        execute=capture_region,
    ),
]
```

When the vision model reasons about what to do, it receives the list of available tools with descriptions. This is the bridge between "library of functions" and "agent that picks actions."

**Not built yet** — implement when we have 3+ action modules. For now, modules are plain functions.

### State & Sessions

Each agent run produces a **session** — a sequence of frozen steps:

```python
@dataclass(frozen=True)
class AgentStep:
    timestamp: float
    screenshot: bytes          # or path to saved image
    reasoning: str             # model's analysis
    action: str                # what was decided
    tool_used: str             # which tool executed it
    success: bool              # did it work

@dataclass(frozen=True)
class Session:
    session_id: str
    steps: tuple[AgentStep, ...]
    started_at: float
    ended_at: float | None
```

Sessions persist as JSON in `~/.assistant/sessions/`. The schema lives in the repo; the data does not.

### User Interaction Model

How does a user interact with the assistant? Four possible interfaces (not mutually exclusive):

| Interface | Use case | Priority |
|-----------|----------|----------|
| **Python API** | `from assistant import capture_screen` — scripting, automations | Now |
| **CLI** | `assistant capture`, `assistant run <automation>` — quick actions from terminal | Soon |
| **Claude Code integration** | Skills/hooks that trigger assistant actions from within Claude Code | Later |
| **Background daemon** | Hotkey-triggered, scheduled, always-on monitoring | Later |

The Python API is the foundation. CLI wraps it. Claude Code integration and daemon are future layers.

### Runtime Data Layout

All runtime data lives in `~/.assistant/` — outside the repo.

```
~/.assistant/
├── captures/           # Screenshots (date-partitioned)
│   └── 2026-04-01/
│       ├── 143052_full.png
│       └── 143055_region.png
├── sessions/           # Agent run logs (JSON per session)
│   └── 2026-04-01_143052_abc123.json
├── config/             # User configuration (future)
└── logs/               # Application logs (future)
```

---

## Feature Ideas

### Screen Module
- **capture_screen** / **capture_region** / **list_monitors** / **save_capture** — Phase 2, ready to implement
- **capture_window(title)** — capture a specific window. Two approaches: geometry-based (simple, needs visible window) vs native X11/Win32 (works on minimized). Needs investigation.
- **list_windows()** — enumerate open windows with title, geometry, PID. Platform-specific.
- **detect_elements(image)** — use vision model to identify UI elements with bounding boxes. Intersection of screen + vision modules.

### Vision Module
- Send PIL Image to Gemini (primary) or other providers
- Get structured response (what's on screen, suggested actions)
- Prompt templates for different analysis types (general, find element, read text)

### Input Module
- Mouse control (move, click, drag)
- Keyboard control (type, hotkeys)
- Platform abstraction (PyAutoGUI or pynput)

### Browser Module
- Playwright-based browser automation
- Browser-Use integration (AI-driven browser control)

### Conversation Memory / RAG System
A local system for maintaining context across conversations:
- **Project-based organization** — group conversations by project/topic
- **Compaction strategies** — different methods for different use cases:
  - Summarization (general conversations)
  - Extraction (e.g., vocabulary lists from language learning sessions)
  - Key decisions / Q&A pairs
- **Research needed**: how do Cursor, Windsurf, Continue.dev, Copilot handle context? What approaches exist beyond RAG (e.g., structured memory, knowledge graphs)?
- This is a feature in its own right, not a foundation piece

---

## GitHub Issues Setup Guide

### Initial Setup

1. **Go to your repo on GitHub** → Settings → Features → make sure Issues is enabled (it is by default)

2. **Create labels** — go to Issues → Labels → "New label":

   | Label | Color | Description |
   |-------|-------|-------------|
   | `feat` | `#1a7f37` (green) | New feature |
   | `fix` | `#d73a4a` (red) | Bug fix |
   | `refactor` | `#0075ca` (blue) | Code improvement |
   | `question` | `#d876e3` (purple) | Needs discussion |
   | `research` | `#f9d0c4` (peach) | Investigation / exploration |
   | `blocked` | `#e4e669` (yellow) | Waiting on something |

   You can delete GitHub's default labels (bug, documentation, duplicate, etc.) — they're generic and overlap with ours.

3. **Create milestone** (optional but useful): Issues → Milestones → "New milestone"
   - Example: `v0.1 — Screen Capture` — group the first batch of issues

### Creating Issues

From the terminal with `gh` CLI:
```bash
# Create a feature issue
gh issue create --title "feat: screen — capture_window()" \
  --body "Capture a specific window by title..." \
  --label "feat"

# Create a research issue
gh issue create --title "research: context management approaches" \
  --body "Explore how Cursor/Windsurf/etc handle conversation context..." \
  --label "research"
```

Or from the GitHub web UI: Issues → "New issue" → fill in title and description.

### Working with Issues

**Starting work on an issue:**
```bash
# Create a branch linked to the issue
git checkout -b feat/capture-window
# ... do work, commit ...
git push -u origin feat/capture-window
```

**Linking commits to issues:**
```bash
git commit -m "feat(screen): add capture_window (fixes #3)"
#                                                ^^^^^^^^
#                              This auto-closes issue #3 when merged to main
```

Other linking keywords: `closes #3`, `resolves #3`, `relates to #3` (links without closing).

**Creating a PR that closes an issue:**
```bash
gh pr create --title "feat(screen): add capture_window" \
  --body "Closes #3\n\n## Summary\n- Added capture_window function\n..."
```

**Checking issue status:**
```bash
gh issue list                    # all open issues
gh issue list --label "feat"     # filtered by label
gh issue view 3                  # details of issue #3
```

### Workflow Summary

```
Issue created → Branch created → Work done → PR opened → Review → Merge → Issue auto-closed
     #3        feat/capture-window   commits    PR #4      tests    squash    #3 closed
```

---

## Issues to Create

After the foundation work is complete, create these initial issues:

1. `feat: screen — capture_window()` — label: `feat`
2. `feat: screen — list_windows()` — label: `feat`
3. `feat: screen — detect_elements()` — label: `feat`
4. `feat: bounded agent loop with stop conditions` — label: `feat`
5. `feat: tool registry pattern` — label: `feat`
6. `feat: session persistence (frozen steps + JSON)` — label: `feat`
7. `feat: CLI interface` — label: `feat`
8. `research: context management / conversation memory approaches` — label: `research`
9. `research: user interaction model (CLI vs daemon vs Claude Code integration)` — label: `research`
