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

Modules (screen, input, vision) shouldn't just be importable functions — they should register as **tools** with metadata. This lets the vision model know what actions are available when reasoning.

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

### How AI Interacts with the Screen

**Focus: desktop apps** (not browser). The challenge is precision — how does the model know exactly where to click?

#### Approaches Researched

| Approach                | How it works                                                                  | Precision                                | Complexity                                  |
| ----------------------- | ----------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------- |
| **Claude Computer Use** | Built-in API tool, model outputs `{action: "left_click", coordinate: [x, y]}` | Good at 1024x768, degrades at higher res | Low — just API calls                        |
| **Grid overlay**        | Draw labeled grid on screenshot, model says "click B3"                        | High — grid cells are unambiguous        | Low — just PIL drawing                      |
| **Adaptive zoom**       | Coarse grid → model picks cell → zoom in → finer grid                         | Very high — two passes                   | Medium — two API calls                      |
| **SoM (Set-of-Mark)**   | Detect UI elements, overlay numbered labels, model says "click #7"            | High — elements are pre-identified       | High — needs ML detection (OmniParser, SAM) |
| **Accessibility APIs**  | Read element tree from OS (AT-SPI on Linux, UI Automation on Windows)         | Pixel-perfect                            | Medium — only works when apps support it    |

#### Our Approach: Grid Overlay + Claude Computer Use

**Two-tier strategy optimized for token efficiency and speed:**

**Tier 1 — Grid overlay (default, fast, cheap):**

1. Capture screenshot at 1024x768
2. Overlay a labeled grid (e.g., 10x8 grid → ~100x96px cells, labeled A1-J8)
3. Send to vision model: "What's on screen? Where should I click to [task]?"
4. Model responds with grid reference: "Click B3 to open the file menu"
5. Calculate center of cell B3, execute click

**Tier 2 — Adaptive refinement (when precision matters):**

1. Same as Tier 1, but after model picks a cell...
2. Capture just that region at full resolution
3. Overlay a finer sub-grid on the zoomed region
4. Model picks the sub-cell → precise coordinates
5. Two API calls, but sub-pixel precision

**Why this over Claude Computer Use raw coordinates:**

- Grid references are unambiguous — "B3" can't drift by 50px
- Works with any vision model (Gemini, Claude, local models), not locked to Claude API
- Fewer tokens — grid labels are concise vs the model reasoning about exact pixel positions
- Adaptive zoom only needed for dense UIs

**Claude Computer Use** remains available as an alternative backend — its structured action format (`left_click`, `type`, `key`, `scroll`) is the action vocabulary we adopt regardless of which approach identifies the target.

#### Action Space

Adopted from Claude Computer Use's structured format:

| Action         | Parameters                      | Description                      |
| -------------- | ------------------------------- | -------------------------------- |
| `left_click`   | `coordinate`                    | Click at position                |
| `right_click`  | `coordinate`                    | Right-click                      |
| `double_click` | `coordinate`                    | Double-click                     |
| `type`         | `text`                          | Type text                        |
| `key`          | `text`                          | Press key combo (e.g., `ctrl+s`) |
| `mouse_move`   | `coordinate`                    | Move cursor                      |
| `scroll`       | `coordinate, direction, amount` | Scroll                           |
| `screenshot`   | none                            | Capture current state            |

#### The Agent Loop

```
while not done and iterations < max_iterations:
    screenshot = capture_screen()
    annotated = overlay_grid(screenshot)

    response = vision_model.analyze(annotated, task, history)

    if response.action == "done":
        break

    execute_action(response.action, response.target)
    log_step(screenshot, response)  # basic JSONL logging from day one

    verify_screenshot = capture_screen()
    # next iteration uses this as the new state
```

#### Industry Context

| Project                 | Approach                                          | What we learn                                              |
| ----------------------- | ------------------------------------------------- | ---------------------------------------------------------- |
| **Claude Computer Use** | Screenshot → model → raw coordinates              | Action format standard; resolution matters (1024x768 best) |
| **browser-use**         | DOM serialization with indices                    | Index-based selection >> coordinate guessing (for web)     |
| **OmniParser**          | YOLO element detection + Florence captioning      | ML-based UI parsing is powerful but heavy                  |
| **Manus AI**            | Code generation (writes Python to interact)       | Sidesteps clicking entirely for some tasks                 |
| **OpenAdapt**           | Record human demos, replay with AI generalization | Different paradigm — learn from demonstration              |

### User Interaction Model

Four interfaces, layered incrementally:

| Interface              | Use case                                                         | Priority |
| ---------------------- | ---------------------------------------------------------------- | -------- |
| **Python API**         | `from assistant import capture_screen` — scripting, automations  | Phase 1  |
| **CLI** (`typer`)      | `assistant capture`, `assistant run <automation>` — terminal use | Phase 2  |
| **Claude Code skills** | `/capture-screen`, `/run-automation` — Claude orchestrates       | Phase 4  |
| **Background daemon**  | Hotkey-triggered, scheduled, always-on monitoring                | Future   |

**How the layers compose:**

- Python API is the foundation — every other layer calls it
- CLI wraps the API with `typer` — portable, testable, works without Claude Code
- Claude Code skills wrap the CLI — a SKILL.md file that calls `assistant <command>` via bash, then Claude reasons about the output

**Example skill (future):**

```yaml
---
name: capture-screen
description: Capture the screen and describe what's visible
allowed-tools: Bash(assistant *)
---
Run: !`assistant capture --monitor 1 --describe`
Analyze the screenshot description and answer the user's question about what's on screen.
```

### Implementation Roadmap

```
Phase 1: Screen capture                 ← capture pixels (mss + PIL)
Phase 2: CLI (typer)                    ← wraps Phase 1
Phase 3: AI screen interaction          ← the core value
  3a: Input module                      ← mouse/keyboard (pyautogui)
  3b: Vision module                     ← send screenshots + grid to models, get actions
  3c: Agent loop + basic JSONL logging  ← capture→reason→act→verify
Phase 4: Claude Code skills             ← SKILL.md files wrapping CLI
Phase 5: Memory/RAG                     ← SQLite FTS5, session summaries, compaction
```

### Runtime Data Layout

All runtime data lives in `~/.assistant/` — outside the repo.

```
~/.assistant/
├── captures/           # Screenshots (date-partitioned)
│   └── 2026-04-01/
│       ├── 143052_full.png
│       └── 143055_region.png
├── sessions/           # Agent run logs (JSONL per session)
│   └── 2026-04-01_143052_abc123.jsonl
├── memory/             # RAG system data (Phase 5)
│   ├── projects/
│   └── global/
├── config/             # User configuration (future)
└── logs/               # Application logs (future)
```

---

## Feature Ideas

### Screen Module

- **capture_screen** / **capture_region** / **list_monitors** / **save_capture** — Phase 1, ready to implement
- **overlay_grid(image, cols, rows)** — draw labeled grid on screenshot for model consumption
- **capture_window(title)** — capture a specific window. Two approaches: geometry-based (simple, needs visible window) vs native X11/Win32 (works on minimized). Needs investigation.
- **list_windows()** — enumerate open windows with title, geometry, PID. Platform-specific.

### Vision Module

- Send annotated screenshot (with grid) to model, get structured action response
- Support multiple backends: Claude Computer Use API, Gemini, local models
- Prompt templates for: general analysis, grid-based targeting, adaptive zoom refinement
- Structured output: action type + target (grid ref or coordinates) + reasoning

### Input Module

- Mouse control (move, click, drag, scroll)
- Keyboard control (type, hotkeys, key combos)
- Platform abstraction (PyAutoGUI — cross-platform)
- Coordinate mapping: grid reference → pixel coordinates

### Agent Loop

- Orchestrate capture → annotate → reason → act → verify
- Bounded execution (max iterations, timeout, stop conditions)
- Basic JSONL session logging from day one
- Frozen AgentStep snapshots for each iteration

### Conversation Memory / RAG System

A local memory system for maintaining context across conversations. Built as a standalone module, usable by the agent but also independently (e.g., for logging any Claude Code session).

**Research completed** — compared Claude Code, Cursor, Windsurf, Copilot, Mem0, Letta/MemGPT, LangChain, LlamaIndex. Key insight: plain text + full-text search covers 80% of retrieval needs. Start simple.

#### What to Store

**Tier 1 — Raw data (append-only, never delete):**

- Full conversation transcripts (structured JSONL)
- Agent action logs (clicks, typed text, navigations — structured events)
- User corrections and feedback (tagged explicitly — highest-value signal)

**Tier 2 — Derived (generated from Tier 1 via LLM):**

- Session summaries (3-5 bullets at session end)
- Extracted facts ("user prefers ruff", "project uses FastAPI")
- Domain-specific extractions (vocabulary, error patterns, decision logs)

#### Image Handling

Strategy: **text description + retention curve**.

| Time          | What's kept                                     |
| ------------- | ----------------------------------------------- |
| At capture    | Full image + text description via vision model  |
| After 7 days  | Description + metadata + downscaled thumbnail   |
| After 30 days | Description + metadata only (unless bookmarked) |

#### Retrieval Strategy (phased)

1. **v1**: SQLite FTS5 — full-text keyword search. Zero new deps.
2. **v2**: Add ChromaDB + sentence-transformers for semantic search.
3. **v3**: Hybrid retrieval (FTS5 + vector) with reciprocal rank fusion.

#### Compaction Strategies

One pipeline, multiple domain-specific plugins:

| Domain            | Extra extraction                  | Output format          |
| ----------------- | --------------------------------- | ---------------------- |
| General           | Decisions, outcomes, open threads | Session summary        |
| Language learning | Vocabulary, grammar corrections   | Flashcard entries      |
| Debugging         | Error signature, root cause, fix  | Problem-solution pairs |
| Code review       | Decisions, patterns established   | Decision log           |

#### Project-Based Organization

```
~/.assistant/memory/
  projects/
    assistant/              ← scoped to this project
      sessions/
      summaries/
      facts.jsonl
    language-japanese/
      sessions/
      vocabulary.jsonl
  global/
    user_profile.jsonl      ← cross-project facts
    corrections.jsonl       ← cross-project preferences
```

#### Cloud Sync

**Syncthing** — zero cloud dependency, automatic, handles mixed content, encrypted, works on WSL2.

#### Industry Comparison

| Tool         | Approach                            | Key insight                     |
| ------------ | ----------------------------------- | ------------------------------- |
| Claude Code  | Plain markdown files, 200-line cap  | Simplicity works                |
| Cursor       | Vector embeddings in Turbopuffer    | Heavy infra for semantic search |
| Copilot      | 28-day expiry + citation validation | Elegant staleness handling      |
| Mem0         | Triple store (vector + graph + KV)  | Captures relationships          |
| Letta/MemGPT | LLM self-manages memory via tools   | Agent controls its own context  |

---

## Future Ideas & Reminders

### Image Comparison for Failure Detection

Use PIL `ImageChops.difference()` to detect whether an action changed the screen — instant, CPU-only, no vision model call. Use cases:
- **Stuck detection**: screen unchanged after action → retry or report stuck
- **Wait-for-load**: compare screenshots until stable (animation finished)
- **Skip unnecessary vision calls**: if nothing changed, don't re-analyze

### Orchestration Strategy Versioning

Store different orchestration strategies as versioned configs so we can A/B test them:

```
automations/strategies/
  simple_click/v1.yaml       # single action per step, basic grid
  form_filling/v1.yaml       # task-specific: fill forms
  form_filling/v2.yaml       # improved version
```

Each strategy defines: prompt template, grid density, model to use, max iterations, verification method. Load by name in the agent loop. Enables comparison between approaches (e.g., "v1: single model" vs "v2: planner + executor" vs "v3: multi-model routing").

### Reference: hermes-agent (NousResearch)

https://github.com/NousResearch/hermes-agent — Notable patterns:
- **Smart model routing**: detects complexity (code blocks, URLs, keywords) to route cheap vs expensive models
- **Memory prefetching**: async context assembly before each turn with fence tags
- **Resilient composition**: memory failures degrade gracefully, don't block execution
- **Metadata-driven skill discovery**: YAML frontmatter for lightweight loading

### Scripts Refinement

Demo scripts (`demo_vision.py`, `demo_agent_interactive.py`) need updating after OpenRouter migration. Defer to later — functional but reference old defaults.
