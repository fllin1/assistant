# LN Voice Over

Converts a light novel into a multi-voice audiobook. Starts from an AnyFlip PDF (via the `/setup-book` skill) or a hand-prepared `.txt` volume, splits it into chapters, parses structural segments (narration, dialogue, inner thoughts), attributes speakers via LLM, and synthesizes audio with per-character TTS voices.

## Series & Volumes

Projects are organized as `<series>/<volume>`. The character registry and voice assignments live at the **series** level, shared across every volume — so that voices stay consistent across a multi-volume light novel. Each volume has its own pipeline I/O.

```
~/.assistant/ln_voice_over/projects/
└── classroom-of-the-elite-year-2/          ← SERIES
    ├── config/
    │   ├── characters.json                  (shared cast)
    │   └── voices.json                      (shared voice assignments)
    ├── v6/                                  ← VOLUME
    │   └── source/ chapters/ cleaned/ ...
    ├── v7/
    └── v9/
```

Standalone books use the same shape with a single volume (e.g. `spice-and-wolf/v1/`). See `docs/7-series-layout.md` for details.

## Pipeline

```
SOURCE → SPLIT → CLEAN → PARSE → EXTRACT → REVIEW → VOICE-ASSIGN → SYNTHESIZE
  │        │        │       │        │        │          │              │
  ▼        ▼        ▼       ▼        ▼        ▼          ▼              ▼
source/  chapters/ cleaned/ parsed/ extracted/ reviewed/ voices.json  audio/
```

Each stage reads from the previous stage's output and writes to its own directory. All intermediate data is stored as inspectable text/JSON files under the volume root; voice assignments live in the series-level `config/voices.json`.

| Stage | What it does | Output directory |
|-------|-------------|-----------------|
| **Source** (`/setup-book`) | Download PDF, extract page images, OCR text, produce `book.json` | `<volume>/source/` |
| **Split** | Split the volume into chapter files (from `book.json` or `.txt`) | `<volume>/chapters/` |
| **Clean** | Remove watermarks, page numbers, collapse blank lines | `<volume>/cleaned/` |
| **Parse** | Segment text into typed blocks (narration, dialogue, etc.) | `<volume>/parsed/` |
| **Extract** | LLM-based speaker attribution per dialogue segment | `<volume>/extracted/` |
| **Review** (`/review-chapter`) | Judge re-attribution, flag diffs, resolve with Opus, write canonical chapter | `<volume>/reviewed/` |
| **Voice Assign** (`/assign-voices`) | Propose + apply per-character voice mappings | `<series>/config/voices.json` |
| **Synthesize** (`lnvo synthesize`) | TTS per segment with per-character voices, assemble audio | `<volume>/audio/` |

## Quick Start

**PDF path (recommended):**

```bash
# 1. Source: download + OCR + structure into book.json
/setup-book https://anyflip.com/cnyjl/fhfw/ classroom-of-the-elite-year-2/v7

# 2. Split, clean, parse (bare `lnvo` opens a guided menu with a picker)
lnvo split classroom-of-the-elite-year-2/v7
lnvo clean classroom-of-the-elite-year-2/v7
lnvo parse classroom-of-the-elite-year-2/v7

# 3. Extract speakers — Claude Sonnet skill (per chapter, parallel agents; auto-detects POV)
/attribute-speakers classroom-of-the-elite-year-2/v7 2

# 4. Review: judge pass catches disagreements, Opus resolves them, writes reviewed/
/review-chapter classroom-of-the-elite-year-2/v7 2

# 5. Assign voices (skill, writes to series config/voices.json)
/assign-voices classroom-of-the-elite-year-2/v7

# 6. Synthesize audio (reads reviewed/, writes audio/)
lnvo synthesize classroom-of-the-elite-year-2/v7
```

The legacy flat slug form (`classroom-of-the-elite-year-2-v7`) is still accepted and auto-split into `<series>/<volume>` under the hood. New projects should use the `series/volume` form directly.

**Manual `.txt` path:** drop a `.txt` file in `<series>/<volume>/source/`, then start at step 2. Split detects chapter boundaries via regex patterns instead of the pre-structured JSON.

## Guided Mode

Typing long slugs gets old. The CLI has three UX affordances:

- **Bare `lnvo`** opens an interactive menu: pick a stage, pick a series, pick a volume, run.
- **Omit the book argument** on any command (`lnvo split`) to get a 2-step picker over existing series and volumes. An argument on the command line (`lnvo split <series>/<volume>`) bypasses the picker.
- **Shorthand accepted:** `<series>/<volume>`, legacy `<series>-v<N>`, or just `<series>` (volume defaults to `v1`).

## CLI Reference

Pipeline stages:

```
lnvo split [<series>/<volume>]
lnvo clean [<series>/<volume>]
lnvo parse [<series>/<volume>]
lnvo extract [<series>/<volume>] --chapter N [--model NAME] [--pov NAME] [--batch-size N] [--verbose]
lnvo synthesize [<series>/<volume>] [--chapter N] [--parallel N] [--no-normalize]
```

Voice management (all write to / read from the **series-level** config):

```
lnvo list-voices [--provider edge|openai|kokoro] [--gender male|female]
lnvo audition <voice-id> [--text "..."] [--character NAME --book <series>/<volume>]
lnvo assign-voice [<series>/<volume>] <character-name> <voice-id> [--provider NAME]
lnvo show-voices [<series>/<volume>]
```

Utility:

```
lnvo                        # guided menu
lnvo list-books             # list all <series>/<volume> pairs
```

Skills:

```
/setup-book       # source acquisition from AnyFlip
/attribute-speakers # speaker attribution via Claude Sonnet
/review-chapter   # resolve flagged divergences
/assign-voices    # propose + apply per-character voice cast
```

## Stage Details

### Stage 1: SPLIT — Volume to Chapters

- **Input**: `source/book.json` (from `/setup-book`) OR `source/*.txt` → **Output**: `chapters/chapter_01.txt`, ..., `chapters/manifest.json`
- JSON input is pre-split with titles; `.txt` input uses regex patterns (`config.CHAPTER_PATTERNS`) to detect chapter boundaries
- `manifest.json` has `pov_character: null` — user fills it manually
- Front matter before first header → `chapter_00.txt` or skipped
- **Sub-chapters**: when a main chapter contains bare `N.M` marker lines (the publisher's POV-shift convention — e.g. `7.1`/`7.2`/`7.3`/`7.4`), split emits one manifest row per sub (`subchapter: M`) and writes `chapter_NN_M.txt`. Triggered only when ≥ 2 markers exist with strictly-increasing minors whose major matches the chapter number; otherwise the chapter stays whole

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
lnvo extract classroom-of-the-elite-year-2/v7 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --batch-size 9999

# Verbose mode (adds reasoning for debugging)
lnvo extract classroom-of-the-elite-year-2/v7 --chapter 02 \
    --model gemini-flash --pov "Ayanokouji Kiyotaka" --verbose
```

**Claude Sonnet skill** (`/attribute-speakers`) — spawns parallel Sonnet agents that each process a chunk of ~80 segments with overlap. Faster for large chapters:

```
/attribute-speakers classroom-of-the-elite-year-2/v7 5
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

### Stage 5: REVIEW — Judge Pass + Canonical Chapter

- **Input**: `extracted/chapter_NN/*.json` (one Sonnet attribution per chapter) → **Output**: `reviewed/chapter_NN.json`
- The `/review-chapter` skill re-attributes each chapter with a shifted-overlap chunking to break any echo-chamber effect, diffs the new pass against the original, then resolves each disagreement with Opus + near-context. Name canonicalisation (against the series `characters.json` registry) happens inside the judge — there is no separate resolve stage

### Stage 7: VOICE ASSIGN — Per-character Voice Mapping

- **Input**: series `config/characters.json` + dialogue counts from all reviewed volumes → **Output**: series `config/voices.json`
- The `/assign-voices` skill is the one-command path; see `docs/6-voice-assignment.md` for the underlying CLI (`lnvo list-voices`, `lnvo audition`, `lnvo assign-voice`, `lnvo show-voices`) and the tiered assignment strategy.
- Written once per series, not per volume. Adding a new volume that introduces new speakers? Rerun `/assign-voices` — existing assignments are preserved and only the newly-seen characters get proposals.

### Stage 8: SYNTHESIZE + ASSEMBLE

- **Input**: `reviewed/*.json` + series `config/voices.json` + series `config/characters.json` → **Output**: `audio/segments/<cache_key>.wav` (per-segment cache) + `audio/chapters/chapter_NN.wav` (assembled) + `audio/chapters/chapter_NN.manifest.json` (segment→voice→file map)
- **Format: WAV end-to-end.** Providers return WAV (OpenAI native, Kokoro native, Edge decodes its MP3 stream once inside the provider). Cache, normalization, concatenation, and final export all stay PCM — no lossy re-encodes. Final chapter files are larger (~10× MP3) but editable in any DAW without generation loss.
- Hard-requires the chapter be in `reviewed/` — run `/review-chapter` first.
- Skips `chapter_00*` (front matter) when no `--chapter` is passed.

```bash
lnvo synthesize classroom-of-the-elite-year-2/v7                  # every reviewed chapter
lnvo synthesize classroom-of-the-elite-year-2/v7 --chapter 01     # one chapter
lnvo synthesize classroom-of-the-elite-year-2/v7 --parallel 8     # more TTS concurrency
lnvo synthesize classroom-of-the-elite-year-2/v7 --no-normalize   # skip loudness flattening
```

#### Voice Resolution

```
scene_break     → silence (no TTS)
chapter_header  → NARRATOR voice
narration       → pov_character voice if set, else NARRATOR
dialogue        → speaker's mapped voice → gender default → NARRATOR
```

#### Caching

`cache_key = sha256(f"{provider}:{voice_id}:{text}:{settings}")[:16]` — content-addressable, provider-scoped so the same voice id across two providers doesn't collide, settings-scoped so a speed change invalidates correctly. Re-runs after fixing one attribution only re-synthesize the changed segment; the chapter WAV is rebuilt from the updated cache.

#### Concurrency

`--parallel N` (default 4) controls TTS concurrency. Kokoro calls share a singleton pipeline that is not thread-safe, so they serialize on an internal semaphore — Edge and OpenAI keep the full pool. Effectively: mixed chapters parallelize, Kokoro-only chapters run single-threaded no matter what you pass.

#### Normalization

Per-segment LUFS normalization to -16 LUFS (Apple Podcasts spec) via `pyloudnorm`, applied before concatenation. This flattens the inherent volume differences between Edge / OpenAI / Kokoro at the level that actually matters (each voice block), instead of a post-hoc whole-chapter gain that can't fix cross-voice jumps. Segments shorter than 1s fall back to peak-based dBFS normalization (LUFS measurement is unreliable on short clips). Pass `--no-normalize` to get raw provider output.

#### Assembly

Concatenate with `pydub`, insert silence between segments:
- 200ms dialogue→dialogue
- 400ms narration↔dialogue
- 800ms scene break
- 1500ms chapter header

Requires `ffmpeg` on PATH: even though the pipeline is WAV-native, the Edge provider still needs ffmpeg (via pydub) to decode its MP3 stream to WAV. The command aborts early with a clear message if missing.

## Project Data Layout

```
~/.assistant/ln_voice_over/projects/<series-slug>/
├── config/                         ← SERIES LEVEL (shared across volumes)
│   ├── characters.json             # character registry (names, aliases, gender)
│   └── voices.json                 # voice mappings per character
└── <volume-slug>/                  ← VOLUME LEVEL (per-volume pipeline I/O)
    ├── source/                     # pipeline input: book.json, PDF, .txt
    ├── chapters/                   # split chapter .txt files + manifest.json
    ├── cleaned/                    # cleaned chapter .txt files
    ├── parsed/                     # structural segments as JSON
    ├── extracted/
    │   └── chapter_NN/              # flat {index: speaker} JSONs per source
    │       └── claude-sonnet_skill_YYYYMMDD.json
    ├── reviewed/                    # user-approved final attributions
    ├── illustrations/               # illustration images + manifest (/setup-book)
    └── audio/
        ├── segments/                # cached per-segment audio files
        └── chapters/                # assembled chapter audio
```

## Character Registry

The registry at `<series>/config/characters.json` maps character names and aliases for resolution:

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
- `docs/7-series-layout.md` — the nested `<series>/<volume>/` directory layout and config sharing
- `.claude/commands/setup-book.md` — the source-acquisition skill itself
- `.claude/commands/assign-voices.md` — the voice-casting skill

## Dependencies

- **typer** — CLI framework
- **openai** — OpenRouter API client (OpenAI-compatible)
- **ollama** — local LLM inference (optional)
- **edge-tts** — TTS provider (free, async)
- **pydub** — audio concatenation
- **rich** — colored CLI output
- **ffmpeg** — system dependency for audio processing
- **opendataloader-pdf** — PDF page extraction (requires Java 21)

## Configuration

API keys are loaded from `.env` at the repo root on `lnvo` startup via `python-dotenv`. Copy the template and fill in:

```bash
cp .env.example .env
# edit .env — add OPENAI_API_KEY and/or OPENROUTER_API_KEY
```

- `OPENAI_API_KEY` — required for OpenAI TTS voices in stage 8 (`lnvo synthesize`).
- `OPENROUTER_API_KEY` — required for cloud extraction models in stage 4 (`lnvo extract`) and cross-validation in stage 5 (`lnvo resolve`).

`.env` is gitignored; `.env.example` is committed as the template.
