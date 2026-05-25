# LN Voice Over

Turns a light novel into per-chapter JSON of typed segments (narration, dialogue, scene breaks, chapter headers), attributes each line to a speaker, and can synthesize reviewed chapters into WAV audio through the companion voice-tuning project.

## Series & Volumes

Projects are organized as `<series>/<volume>`. The character registry lives at the **series** level, shared across every volume. Each volume has its own pipeline I/O.

```
~/.assistant/ln_voice_over/projects/
└── classroom-of-the-elite-year-2/          ← SERIES
    ├── config/
    │   └── characters.json                  (shared cast)
    ├── v6/                                  ← VOLUME
    │   └── source/ chapters/ parsed/ extracted/ reviewed/ illustrations/
    ├── v7/
    └── v9/
```

Standalone books use the same shape with a single volume (e.g. `spice-and-wolf/v1/`). See `docs/7-series-layout.md` for details.

## Pipeline

```
SOURCE → SPLIT → PARSE → EXTRACT → REVIEW → SYNTHESIS
  │        │       │        │        │          │
  ▼        ▼       ▼        ▼        ▼          ▼
source/  chapters/ parsed/ extracted/ reviewed/ audio/
```

Each stage reads from the previous stage's output and writes to its own directory. All intermediate data is stored as inspectable text/JSON files under the volume root.

| Stage | What it does | Output directory |
|-------|-------------|-----------------|
| **Source** (`/setup-book`) | Download PDF, extract page images, OCR text, produce `book.json` | `<volume>/source/` |
| **Split** (`lnvo split`) | Split the volume into chapter files (from `book.json` or `.txt`) | `<volume>/chapters/` |
| **Parse** (`lnvo parse`) | Clean artifacts + segment text into typed blocks (narration, dialogue, etc.) | `<volume>/parsed/` |
| **Extract** (`/attribute-speakers`) | Claude Sonnet skill: parallel agents attribute each dialogue line | `<volume>/extracted/` |
| **Review** (`/review-attribution`) | Judge re-attribution, flag diffs, resolve with Opus, write canonical chapter | `<volume>/reviewed/` |
| **Synthesis** (`lnvo synthesize`) | Validate canonical reviewed data, render TTS stems, concatenate chapter WAV | `<volume>/audio/` |

## Quick Start

**PDF path (recommended):**

```bash
# 1. Source: download + OCR + structure into book.json
/setup-book https://anyflip.com/cnyjl/fhfw/ classroom-of-the-elite-year-2/v7

# 2. Split + parse (bare `lnvo` opens a guided menu with a picker)
lnvo split classroom-of-the-elite-year-2/v7
lnvo parse classroom-of-the-elite-year-2/v7

# 3. Extract speakers — Claude Sonnet skill (per chapter, parallel agents; auto-detects Narrator)
/attribute-speakers classroom-of-the-elite-year-2/v7 2

# 4. Review: judge pass catches disagreements, Opus resolves them, writes reviewed/
/review-attribution classroom-of-the-elite-year-2/v7 2

# 5. Import accepted cast, then synthesize reviewed audio
lnvo voice-map import classroom-of-the-elite-year-2
lnvo synthesize classroom-of-the-elite-year-2/v7 2
```

The legacy flat slug form (`classroom-of-the-elite-year-2-v7`) is still accepted and auto-split into `<series>/<volume>` under the hood. New projects should use the `series/volume` form directly.

**Manual `.txt` path:** drop a `.txt` file in `<series>/<volume>/source/`, then start at step 2. Split detects chapter boundaries via regex patterns instead of the pre-structured JSON.

## Guided Mode

Typing long slugs gets old. The CLI has three UX affordances:

- **Bare `lnvo`** opens an interactive menu: pick a stage, pick a series, pick a volume, run.
- **Omit the book argument** on any command (`lnvo split`) to get a 2-step picker over existing series and volumes. An argument on the command line (`lnvo split <series>/<volume>`) bypasses the picker.
- **Shorthand accepted:** `<series>/<volume>`, legacy `<series>-v<N>`, or just `<series>` (volume defaults to `v1`).

## CLI Reference

```
lnvo                        # guided menu
lnvo list-books             # list all <series>/<volume> pairs
lnvo split [<series>/<volume>]
lnvo parse [<series>/<volume>]
lnvo voice-map import <series>
lnvo synthesize <series>/<volume> <chapter_id>
```

Skills:

```
/setup-book           # source acquisition from AnyFlip
/attribute-speakers   # speaker attribution via Claude Sonnet
/review-attribution   # resolve flagged divergences
```

## Stage Details

### Stage 1: SPLIT — Volume to Chapters

- **Input**: `source/book.json` (from `/setup-book`) OR `source/*.txt` → **Output**: `chapters/chapter_01.txt`, ..., `chapters/manifest.json`
- JSON input is pre-split with titles; `.txt` input uses regex patterns (`config.CHAPTER_PATTERNS`) to detect chapter boundaries
- `manifest.json` has `narrator_status: "unset"` and `narrator: null` — filled in by `/attribute-speakers` when it detects the chapter Narrator
- Front matter before first header → `chapter_00.txt` or skipped
- **Sub-chapters**: when a main chapter contains bare `N.M` marker lines (the publisher's Narrator-shift convention — e.g. `7.1`/`7.2`/`7.3`/`7.4`), split emits one manifest row per sub (`subchapter: M`) and writes `chapter_NN_M.txt`. Triggered only when ≥ 2 markers exist with minors exactly `1..N` and a major number that matches the chapter number; otherwise the chapter stays whole

### Stage 2: PARSE — Cleanup + Structural Segmentation

- **Input**: `chapters/*.txt` → **Output**: `parsed/chapter_01.json`
- Cleanup in-stage: strip watermarks and standalone page numbers, collapse 3+ blank lines to 2, preserve scene breaks (`***`, `---`, `* * *`, etc.), normalize UTF-8
- Segment types: `narration`, `dialogue`, `scene_break`, `chapter_header`
- Split at paragraph boundaries; each dialogue block = one segment
- **No mid-sentence splitting**: `She said "hello" and walked away.` stays as one `narration` segment
- Long narration (>500 chars) split at sentence boundaries

### Stage 3: EXTRACT — Speaker Attribution

The `/attribute-speakers` Claude Sonnet skill spawns parallel Sonnet agents that each process a chunk of ~80 segments with overlap, merges the results, and writes a flat `{index: speaker}` JSON to `extracted/chapter_NN/`. The skill also auto-detects the Narrator and persists it to the manifest as a side effect.

```
/attribute-speakers classroom-of-the-elite-year-2/v7 5
```

### Stage 4: REVIEW — Judge Pass + Canonical Chapter

- **Input**: `extracted/chapter_NN/*.json` (one Sonnet attribution per chapter) → **Output**: `reviewed/chapter_NN.json`
- The `/review-attribution` skill re-attributes each chapter with a shifted-overlap chunking to break any echo-chamber effect, diffs the new pass against the original, then resolves each disagreement with Opus + near-context. Name canonicalisation (against the series `characters.json` registry) happens inside the judge — there is no separate resolve stage.

### Stage 5: SYNTHESIS — Reviewed Chapter to WAV

- **Input**: `reviewed/chapter_NN[_M].json` + series `config/voice_mapping.json` → **Output**: `audio/chapter_NN[_M].wav`
- `lnvo voice-map import <series>` imports accepted cast rows from `/Users/regiswoof/_workspace/tools/voice-tuning/voice-tuning.db` into the series voice mapping.
- `lnvo synthesize <series>/<volume> <chapter_id>` performs strict preflight before audio: reviewed speaker grammar, narrator detection, voice mapping coverage, and voice-tuning engine availability must all pass.
- Dialogue text has only one balanced outer quote pair stripped before TTS; narration and chapter headers are passed verbatim.

## Project Data Layout

```
~/.assistant/ln_voice_over/projects/<series-slug>/
├── config/                         ← SERIES LEVEL (shared across volumes)
│   ├── characters.json             # character registry (names, aliases, gender)
│   └── voice_mapping.json           # accepted synthesis voices
└── <volume-slug>/                  ← VOLUME LEVEL (per-volume pipeline I/O)
    ├── source/                     # pipeline input: book.json, PDF, .txt
    ├── chapters/                   # split chapter .txt files + manifest.json
    ├── parsed/                     # structural segments as JSON (includes cleanup)
    ├── extracted/
    │   └── chapter_NN/             # flat {index: speaker} JSONs per source
    │       └── claude-sonnet_skill_YYYYMMDD.json
    ├── reviewed/                   # canonical final attributions
    ├── illustrations/              # illustration images + manifest (/setup-book)
    └── audio/                      # synthesis cache, stems, manifests, chapter WAVs
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

- `docs/architecture.md` — code organization, data-flow contracts, module interface cards, and generated fact maps
- `docs/0-source-acquisition.md` — prerequisites for `/setup-book` (anyflip-downloader, Java 21)
- `docs/7-series-layout.md` — the nested `<series>/<volume>/` directory layout and config sharing
- `.claude/commands/setup-book.md` — the source-acquisition skill
- `.claude/commands/attribute-speakers.md` — the speaker-attribution skill
- `.claude/commands/review-attribution.md` — the review skill

## Dependencies

- **typer** — CLI framework
- **pydantic** — data models
- **python-dotenv** — env loading
- **opendataloader-pdf** — PDF page extraction, used by `/setup-book` (requires Java 21)
- **voice-tuning** — companion TTS execution project for Kokoro, Orpheus, and Hume
