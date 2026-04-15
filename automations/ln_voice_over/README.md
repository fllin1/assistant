# LN Voice Over

Converts raw light novel text files into multi-voice audiobooks. The pipeline splits a volume into chapters, cleans text artifacts, parses structural segments (narration, dialogue, inner thoughts), attributes speakers via LLM, and synthesizes audio with per-character TTS voices.

## Pipeline

```
SPLIT → CLEAN → PARSE → EXTRACT → RESOLVE → REVIEW → SYNTHESIZE
```

Each stage reads from the previous stage's output and writes to its own directory. All intermediate data is stored as inspectable text/JSON files under `~/.assistant/ln_voice_over/projects/<book-slug>/`.

| Stage | What it does | Output directory |
|-------|-------------|-----------------|
| **Split** | Detect chapter boundaries, split volume `.txt` into chapters | `chapters/` |
| **Clean** | Remove watermarks, page numbers, collapse blank lines | `cleaned/` |
| **Parse** | Segment text into typed blocks (narration, dialogue, etc.) | `parsed/` |
| **Extract** | LLM-based speaker attribution per dialogue segment | `extracted/` |
| **Resolve** | Cross-validate sources, resolve names via character registry | `attributed/` |
| **Review** | Review and correct flagged attributions | `reviewed/` |
| **Synthesize** | TTS per segment with per-character voices, assemble audio | `audio/` |

## Quick Start

```bash
# 1. Create project and place your .txt volume in raw/
lnvo init

# 2. Split, clean, parse
lnvo split classroom-of-the-elite-year-2
lnvo clean classroom-of-the-elite-year-2
lnvo parse classroom-of-the-elite-year-2

# 3. Extract speakers (two independent sources for cross-validation)
# Source A: Gemini Flash via OpenRouter (all chapters, sequential)
python -m automations.ln_voice_over.scripts.run_all_extractions \
    --model gemini-flash --no-resolve

# Source B: Claude Sonnet via /attribute-chapter skill (per chapter)
/attribute-chapter classroom-of-the-elite-year-2 2

# 4. Resolve: cross-validate sources and map to canonical names
python -m automations.ln_voice_over.scripts.run_all_extractions --resolve-only

# 5. Review divergences (next step — Claude skill, not yet implemented)
# 6. Synthesize audio (not yet implemented)
```

## Extraction

Speaker extraction determines who speaks each dialogue segment by analyzing surrounding narration for speech tags, pronouns, and conversational flow.

### Two Extraction Methods

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

### Batch Extraction

Run all chapters with a given model:

```bash
# All chapters with Gemini Flash
python -m automations.ln_voice_over.scripts.run_all_extractions --model gemini-flash

# Specific chapters
python -m automations.ln_voice_over.scripts.run_all_extractions \
    --model gemini-flash --chapters 1,3,5

# Skip extraction, just resolve + diagnose
python -m automations.ln_voice_over.scripts.run_all_extractions --resolve-only
```

## Resolution

The resolve step cross-validates multiple extraction sources and maps raw speaker names to canonical character names from the registry.

```bash
# Resolve a single chapter with specific sources
lnvo resolve classroom-of-the-elite-year-2 --chapter 02 \
    --source gemini-flash_fast_20260414 \
    --source claude-sonnet_skill_20260415

# Resolve all chapters (uses all available sources per chapter)
python -m automations.ln_voice_over.scripts.run_all_extractions --resolve-only
```

### Cross-Validation Behavior

When two sources are available:
- **Both agree** (after canonical name resolution) → consensus, no flag
- **One says "Unknown", other finds a registry name** → prefer the named attribution
- **Both say "Unknown"** → confirmed unknown (no flag — genuinely unnamed speaker)
- **Sources disagree** → flagged as divergence, majority wins

### Flags

The resolve step writes a `_flags.json` file alongside each attributed chapter:

| Flag type | Meaning |
|-----------|---------|
| `divergence` | Sources disagreed on the speaker |
| `unknown` | Single-source Unknown (not confirmed by second source) |
| `unresolved` | Name not found in character registry |
| `missing` | No source had an attribution for this dialogue |

## Review

> **Note:** The review step will be handled by a Claude skill (`/review-chapter` or similar) that reads the attributed chapter + flags, examines the surrounding narration context, and resolves the remaining divergences. This is the next feature to implement.

The review step takes the attributed chapters (with flags) and produces final reviewed chapters. The flags file tells you exactly which segments need attention — typically 1-3% of all dialogues.

## Project Data Layout

```
~/.assistant/ln_voice_over/projects/<book-slug>/
├── config/
│   ├── characters.json      # character registry (names, aliases, gender)
│   ├── voices.json          # voice mappings per character
│   └── extractions/         # config sidecars for extraction runs
├── raw/                     # original volume .txt files
├── chapters/                # split chapter .txt files + manifest.json
├── cleaned/                 # cleaned chapter .txt files
├── parsed/                  # structural segments as JSON
├── extracted/
│   └── chapter_NN/          # flat {index: speaker} JSONs per source
│       ├── gemini-flash_fast_YYYYMMDD.json
│       ├── gemini-flash_fast_YYYYMMDD_config.json
│       └── claude-sonnet_skill_YYYYMMDD.json
├── attributed/              # resolved chapters + flags
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
