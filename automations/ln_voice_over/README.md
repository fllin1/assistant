# LN Voice Over

Converts raw light novel text files into multi-voice audiobooks. The pipeline splits a volume into chapters, cleans text artifacts, parses structural segments (narration, dialogue, inner thoughts), attributes speakers via LLM, and synthesizes audio with per-character TTS voices.

## Pipeline

```
SPLIT → CLEAN → PARSE → EXTRACT → RESOLVE → REVIEW → SYNTHESIZE
  │        │        │         │         │         │          │
  ▼        ▼        ▼         ▼         ▼         ▼          ▼
chapters/ cleaned/ parsed/  extracted/ resolved/ reviewed/ audio/
(txt)    (txt)    (json)   (json)     (json)      (json)    (mp3)
```

Each stage reads from the previous stage's output and writes to its own directory. All intermediate data is stored as inspectable text/JSON files under `~/.assistant/ln_voice_over/projects/<book-slug>/`.

| Stage | What it does | Output directory |
|-------|-------------|-----------------|
| **Split** | Detect chapter boundaries, split volume `.txt` into chapters | `chapters/` |
| **Clean** | Remove watermarks, page numbers, collapse blank lines | `cleaned/` |
| **Parse** | Segment text into typed blocks (narration, dialogue, etc.) | `parsed/` |
| **Extract** | LLM-based speaker attribution per dialogue segment | `extracted/` |
| **Resolve** | Cross-validate sources, resolve names via character registry | `resolved/` |
| **Review** | Review and correct flagged attributions | `reviewed/` |
| **Synthesize** | TTS per segment with per-character voices, assemble audio | `audio/` |

## Quick Start

```bash
# 1. Create project and place your .txt volume or PDF in source/
lnvo init

# 2. Split, clean, parse
lnvo split classroom-of-the-elite-year-2
lnvo clean classroom-of-the-elite-year-2
lnvo parse classroom-of-the-elite-year-2

# 3. Extract speakers (two independent sources for cross-validation)
# Source A: Gemini Flash via OpenRouter
lnvo extract classroom-of-the-elite-year-2 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --batch-size 9999

# Source B: Claude Sonnet via /attribute-chapter skill (per chapter)
/attribute-chapter classroom-of-the-elite-year-2 2

# 4. Resolve: cross-validate sources and map to canonical names
lnvo resolve classroom-of-the-elite-year-2 --chapter 02 \
    --source gemini-flash_fast_20260414 \
    --source claude-sonnet_skill_20260415

# 5. Review divergences
/review-chapter classroom-of-the-elite-year-2 2

# 6. Synthesize audio (not yet implemented)
```

## Stage Details

### Stage 1: SPLIT — Volume to Chapters

- **Input**: `source/book.json` (from `/setup-book`) OR `source/*.txt` → **Output**: `chapters/chapter_01.txt`, ..., `chapters/manifest.json`
- JSON input is pre-split with titles; `.txt` input uses regex patterns (`config.CHAPTER_PATTERNS`) to detect chapter boundaries
- `manifest.json` has `pov_character: null` — user fills it manually
- Front matter before first header → `chapter_00.txt` or skipped

### Stage 2: CLEAN — Artifact Removal

- **Input**: `chapters/*.txt` → **Output**: `cleaned/*.txt`
- Remove watermark lines, standalone page numbers
- Collapse 3+ blank lines to 2
- Preserve scene breaks (`***`, `---`, `* * *`, etc.)
- Normalize encoding to UTF-8

### Stage 3: PARSE — Structural Segmentation

- **Input**: `cleaned/*.txt` → **Output**: `parsed/chapter_01.json`
- Segment types: `narration`, `dialogue`, `inner_thought`, `scene_break`, `chapter_header`
- Split at paragraph boundaries; each dialogue block = one segment
- **No mid-sentence splitting**: `She said "hello" and walked away.` stays as one `narration` segment
- Long narration (>500 chars) split at sentence boundaries

### Stage 4: EXTRACT — Speaker Attribution

Per-dialogue LLM extraction via `extraction.py`. Supports local (Ollama) and cloud (OpenRouter) models.

**CLI extraction** (`lnvo extract`) — runs a local or cloud LLM per-dialogue with a configurable context window:

```bash
# Gemini Flash (cloud, via OpenRouter)
lnvo extract classroom-of-the-elite-year-2 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --batch-size 9999

# Verbose mode (adds reasoning for debugging)
lnvo extract classroom-of-the-elite-year-2 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --verbose
```

**Claude Sonnet skill** (`/attribute-chapter`) — spawns parallel Sonnet agents that each process a chunk of ~80 segments with overlap. Faster for large chapters:

```
/attribute-chapter classroom-of-the-elite-year-2 5
```

Both methods produce the same output format: a flat `{index: speaker}` JSON in `extracted/chapter_NN/`.

#### Model Registry (`config.py`)

Models are registered as `alias → (provider, model_id)`:

| Alias | Provider | Notes |
|-------|----------|-------|
| `gemini-flash` | OpenRouter | 100% accuracy on chapter 2 ground truth |
| `gemini-flash-lite` | OpenRouter | Faster/cheaper, lower accuracy |
| `gemma4:26b` | Ollama | Local, no API key needed |
| `gemma4:12b` | Ollama | Smaller local model |
| `grok-fast` | OpenRouter | Fast cloud alternative |

#### LLM Routing (`llm.py`)

`call_llm()` resolves the model alias via `MODEL_REGISTRY`, then dispatches to `_call_ollama()` or `_call_openrouter()`. Cloud models require `OPENROUTER_API_KEY`.

### Stage 5: RESOLVE — Cross-Validation & Name Resolution

The resolve step cross-validates multiple extraction sources and maps raw speaker names to canonical character names from the registry.

```bash
lnvo resolve classroom-of-the-elite-year-2 --chapter 02 \
    --source gemini-flash_fast_20260414 \
    --source claude-sonnet_skill_20260415
```

#### Cross-Validation Behavior

When two sources are available:
- **Both agree** (after canonical name resolution) → consensus, no flag
- **One says "Unknown", other finds a registry name** → prefer the named attribution
- **Both say "Unknown"** → confirmed unknown (no flag — genuinely unnamed speaker)
- **Sources disagree** → flagged as divergence, majority wins

#### Flags

The resolve step writes a `_flags.json` file alongside each resolved chapter:

| Flag type | Meaning |
|-----------|---------|
| `divergence` | Sources disagreed on the speaker |
| `unknown` | Single-source Unknown (not confirmed by second source) |
| `unresolved` | Name not found in character registry |
| `missing` | No source had an attribution for this dialogue |

### Stage 6: REVIEW — Manual Correction (not yet implemented)

- **Input**: `resolved/*.json` + `resolved/*_flags.json` → **Output**: `reviewed/*.json`
- The `/review-chapter` Claude skill reads context and resolves divergences
- The flags file tells you exactly which segments need attention — typically 1-3% of all dialogues

### Stage 7: SYNTHESIZE + ASSEMBLE (not yet implemented)

- **Input**: `reviewed/*.json` + `config/voices.json` → **Output**: `audio/chapters/*.mp3`

#### Voice Resolution

```
scene_break     → silence (no TTS)
chapter_header  → NARRATOR voice
narration       → pov_character voice if set, else NARRATOR
dialogue/thought → speaker's mapped voice → gender default → NARRATOR
```

#### Caching

`cache_key = sha256(f"{voice_id}:{text}")[:16]` — content-addressable.
Re-runs after fixing one attribution only re-synthesize changed segments.

#### Assembly

Concatenate with `pydub`, insert silence between segments:
- 200ms dialogue→dialogue
- 400ms narration↔dialogue
- 800ms scene break
- 1500ms chapter header

## Project Data Layout

```
~/.assistant/ln_voice_over/projects/<book-slug>/
├── config/
│   ├── characters.json      # character registry (names, aliases, gender)
│   ├── voices.json          # voice mappings per character
│   └── extractions/         # config sidecars for extraction runs
├── source/                  # pipeline input: book.json, PDF, .txt, or extracted pages
├── chapters/                # split chapter .txt files + manifest.json
├── cleaned/                 # cleaned chapter .txt files
├── parsed/                  # structural segments as JSON
├── extracted/
│   └── chapter_NN/          # flat {index: speaker} JSONs per source
│       ├── gemini-flash_fast_YYYYMMDD.json
│       ├── gemini-flash_fast_YYYYMMDD_config.json
│       └── claude-sonnet_skill_YYYYMMDD.json
├── resolved/              # resolved chapters + flags
│   ├── chapter_NN.json      # full chapter with speaker attributions
│   └── chapter_NN_flags.json # divergences and issues to review
├── reviewed/                # user-approved final attributions
└── audio/
    ├── segments/            # cached per-segment audio files
    └── chapters/            # assembled chapter audio
```

## Character Registry

The registry at `config/characters.json` maps character names and aliases for resolution:

```json
{
  "characters": [
    {
      "name": "Horikita Suzune",
      "aliases": ["Horikita", "Suzune"],
      "gender": "female",
      "role": "main"
    }
  ]
}
```

Name matching is layered: exact match → alias match → honorific stripping (`-sensei`, `-kun`, etc.) → component match ("Kiriyama" matches "Kiriyama Ikuto") → fuzzy match (difflib).

## Dependencies

- **typer** — CLI framework
- **openai** — OpenRouter API client (OpenAI-compatible)
- **ollama** — local LLM inference (optional)
- **edge-tts** — TTS provider (free, async)
- **pydub** — audio concatenation
- **rich** — colored CLI output
- **ffmpeg** — system dependency for audio processing

Cloud models require `OPENROUTER_API_KEY` environment variable.
