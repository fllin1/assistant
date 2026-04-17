# LN Voice Over

Converts a light novel into a multi-voice audiobook. Starts from an AnyFlip PDF (via the `/setup-book` skill) or a hand-prepared `.txt` volume, splits it into chapters, parses structural segments (narration, dialogue, inner thoughts), attributes speakers via LLM, and synthesizes audio with per-character TTS voices.

## Pipeline

```
SOURCE → SPLIT → CLEAN → PARSE → EXTRACT → RESOLVE → REVIEW → SYNTHESIZE
  │        │        │       │        │         │         │          │
  ▼        ▼        ▼       ▼        ▼         ▼         ▼          ▼
source/  chapters/ cleaned/ parsed/ extracted/ resolved/ reviewed/ audio/
(pdf,    (txt)    (txt)    (json)  (json)     (json)    (json)    (mp3)
json,
txt)
```

Each stage reads from the previous stage's output and writes to its own directory. All intermediate data is stored as inspectable text/JSON files under `~/.assistant/ln_voice_over/projects/<book-slug>/`.

| Stage | What it does | Output directory |
|-------|-------------|-----------------|
| **Source** (`/setup-book`) | Download PDF, extract page images, OCR text, produce `book.json` | `source/` |
| **Split** | Split the volume into chapter files (from `book.json` or `.txt`) | `chapters/` |
| **Clean** | Remove watermarks, page numbers, collapse blank lines | `cleaned/` |
| **Parse** | Segment text into typed blocks (narration, dialogue, etc.) | `parsed/` |
| **Extract** | LLM-based speaker attribution per dialogue segment | `extracted/` |
| **Resolve** | Cross-validate sources, resolve names via character registry | `resolved/` |
| **Review** (not yet implemented) | Review and correct flagged attributions | `reviewed/` |
| **Synthesize** (not yet implemented) | TTS per segment with per-character voices, assemble audio | `audio/` |

## Quick Start

**PDF path (recommended):**

```bash
# 1. Source: download + OCR + structure into book.json
/setup-book https://anyflip.com/cnyjl/fhfw/ classroom-of-the-elite-year-2-v7

# 2. Split, clean, parse (bare `lnvo` opens a guided menu with a slug picker)
lnvo split classroom-of-the-elite-year-2-v7
lnvo clean classroom-of-the-elite-year-2-v7
lnvo parse classroom-of-the-elite-year-2-v7

# 3. Extract speakers — two independent sources for cross-validation
#    (a) Cloud model via OpenRouter
lnvo extract classroom-of-the-elite-year-2-v7 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --batch-size 9999
#    (b) Claude Sonnet skill (per chapter, parallel agents)
/attribute-chapter classroom-of-the-elite-year-2-v7 2

# 4. Resolve: cross-validate and map to canonical names
lnvo resolve classroom-of-the-elite-year-2-v7 --chapter 02 \
    --source gemini-flash_fast_20260414 \
    --source claude-sonnet_skill_20260415

# 5. Review divergences (skill, writes to reviewed/)
/review-chapter classroom-of-the-elite-year-2-v7 2

# 6. Synthesize audio (not yet implemented)
```

**Manual `.txt` path:** drop a `.txt` file in `source/`, then start at step 2. Split detects chapter boundaries via regex patterns instead of the pre-structured JSON.

## Guided Mode

Typing long slugs gets old. The CLI has two UX affordances:

- **Bare `lnvo`** opens an interactive menu: pick a stage, pick a book, run. If no projects exist yet, it prompts you to create one inline.
- **Omit the slug** on any command (`lnvo split`) to get a numbered picker over existing projects. Slugs on the command line (`lnvo split my-slug`) still work and bypass the picker.

## CLI Reference

Pipeline stages:

```
lnvo split [book-slug]
lnvo clean [book-slug]
lnvo parse [book-slug]
lnvo extract [book-slug] --chapter N [--model NAME] [--pov NAME] [--batch-size N] [--verbose]
lnvo resolve [book-slug] --chapter N --source NAME [--source NAME ...]
```

Voice management:

```
lnvo list-voices [--provider edge|openai|kokoro] [--gender male|female]
lnvo audition <voice-id> [--text "..."] [--character NAME --book SLUG]
lnvo assign-voice [book-slug] <character-name> <voice-id> [--provider NAME]
lnvo show-voices [book-slug]
```

Utility:

```
lnvo                        # guided menu
lnvo list-books             # list all project slugs
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
- Segment types: `narration`, `dialogue`, `scene_break`, `chapter_header`
- Split at paragraph boundaries; each dialogue block = one segment
- **No mid-sentence splitting**: `She said "hello" and walked away.` stays as one `narration` segment
- Long narration (>500 chars) split at sentence boundaries

### Stage 4: EXTRACT — Speaker Attribution

Per-dialogue LLM extraction via `extraction.py`. Supports local (Ollama) and cloud (OpenRouter) models.

**CLI extraction** (`lnvo extract`) — runs a local or cloud LLM per-dialogue with a configurable context window:

```bash
# Gemini Flash (cloud, via OpenRouter)
lnvo extract classroom-of-the-elite-year-2-v7 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --batch-size 9999

# Verbose mode (adds reasoning for debugging)
lnvo extract classroom-of-the-elite-year-2-v7 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --verbose
```

**Claude Sonnet skill** (`/attribute-chapter`) — spawns parallel Sonnet agents that each process a chunk of ~80 segments with overlap. Faster for large chapters:

```
/attribute-chapter classroom-of-the-elite-year-2-v7 5
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
lnvo resolve classroom-of-the-elite-year-2-v7 --chapter 02 \
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
- The flags file tells you exactly which segments need attention — typically 1–3% of all dialogues

### Stage 7: SYNTHESIZE + ASSEMBLE (not yet implemented)

- **Input**: `reviewed/*.json` + `config/voices.json` → **Output**: `audio/chapters/*.mp3`
- See `docs/6-voice-assignment.md` for the voice browsing + assignment workflow (which IS implemented and ready to use)

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
├── resolved/                # resolved chapters + flags
│   ├── chapter_NN.json      # full chapter with speaker attributions
│   └── chapter_NN_flags.json # divergences and issues to review
├── reviewed/                # user-approved final attributions
├── illustrations/           # illustration images + manifest (from /setup-book)
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

## Further Reading

- `docs/0-source-acquisition.md` — prerequisites for `/setup-book` (anyflip-downloader, Java 21)
- `docs/6-voice-assignment.md` — voice browsing, auditioning, and assignment workflow
- `.claude/commands/setup-book.md` — the source-acquisition skill itself

## Dependencies

- **typer** — CLI framework
- **openai** — OpenRouter API client (OpenAI-compatible)
- **ollama** — local LLM inference (optional)
- **edge-tts** — TTS provider (free, async)
- **pydub** — audio concatenation
- **rich** — colored CLI output
- **ffmpeg** — system dependency for audio processing
- **opendataloader-pdf** — PDF page extraction (requires Java 21)

Cloud models require `OPENROUTER_API_KEY` environment variable.
