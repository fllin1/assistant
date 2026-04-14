# LN Voice Over

Converts raw light novel text files into multi-voice audiobooks. The pipeline splits a volume into chapters, cleans text artifacts, parses structural segments (narration, dialogue, inner thoughts), attributes speakers via LLM, and synthesizes audio with per-character TTS voices.

## Pipeline

```
SPLIT → CLEAN → PARSE → ATTRIBUTE → REVIEW → SYNTHESIZE
```

Each stage reads from the previous stage's output and writes to its own directory. All intermediate data is stored as inspectable text/JSON files under `~/.assistant/ln_voice_over/projects/<book-slug>/`.

| Stage | What it does |
|-------|-------------|
| **Split** | Detect chapter boundaries and split a volume `.txt` into individual chapter files |
| **Clean** | Remove watermarks, page numbers, collapse excessive blank lines |
| **Parse** | Segment text into typed blocks: narration, dialogue, inner thought, scene break, chapter header |
| **Attribute** | Assign speakers to dialogue segments (see Attribution Pipeline below) |
| **Review** | Interactive CLI for reviewing and correcting speaker attributions |
| **Synthesize** | TTS synthesis per segment with per-character voices, then assemble into chapter audio files |

## Attribution Pipeline

Speaker attribution uses a two-step process with local LLMs via Ollama.

**Step 1 — Mention Extraction** (`extraction.py`): For each dialogue, an LLM analyzes surrounding narration to find speech tags ("said Horikita", "she replied", "I asked") and determine who is speaking. Two models (gemma4:26b, qwen3.5:27b) cross-validate; disagreements get a verification pass.

**Step 2 — Entity Resolution** (planned): Maps extracted mentions to canonical character registry names. Direct name matches are handled by regex/alias lookup; pronouns and ambiguous cases use AI resolution.

An experiment framework supports iterative prompt development: versioned prompts, batch processing, and ground truth comparison.

## CLI Commands

```bash
# Project setup
lnvo init                          # create a new project
lnvo list-books                    # list existing projects

# Run pipeline stages
lnvo split <book-slug>             # stage 1: volume → chapters
lnvo clean <book-slug>             # stage 2: remove artifacts
lnvo parse <book-slug>             # stage 3: text → typed segments
lnvo attribute <book-slug>         # stage 4: legacy attribution (windowed)
lnvo attribute <book-slug> --per-dialogue --context-size 5  # per-dialogue mode

# Extraction experiments (new two-step pipeline)
lnvo extract <book-slug> --chapter 2 --model gemma4:26b --prompt-version v1
lnvo extract <book-slug> --chapter 2 --batch-start 100 --batch-size 100
lnvo compare <book-slug> <experiment-id>   # compare against ground truth

# Review and synthesis
lnvo review <book-slug>            # stage 5: interactive review
lnvo synthesize <book-slug>        # stage 6: TTS + audio assembly

# Full pipeline
lnvo run-all <book-slug>
```

## Getting Started

1. Run `lnvo init` to create a project (e.g., "classroom-of-the-elite-year-2").
2. Place your `.txt` volume file in `~/.assistant/ln_voice_over/projects/<slug>/raw/`.
3. Edit `config/characters.json` with the book's characters (names, aliases, gender).
4. Set `pov_character` in `chapters/manifest.json` after splitting.
5. Run the pipeline stage by stage, or use `lnvo run-all <slug>`.

## Project Data Layout

```
~/.assistant/ln_voice_over/projects/<book-slug>/
├── config/
│   ├── characters.json      # character registry (names, aliases, gender)
│   └── voices.json          # voice mappings per character
├── raw/                     # original volume .txt files
├── chapters/                # split chapter .txt files + manifest.json
├── cleaned/                 # cleaned chapter .txt files
├── parsed/                  # structural segments as JSON
├── attributed/              # segments with speaker attribution as JSON
├── reviewed/                # user-approved segments as JSON
├── experiments/
│   └── extraction/          # Step 1 experiment runs (config + results per batch)
├── ground_truth_*.json      # manually verified attributions for evaluation
└── audio/
    ├── segments/            # cached per-segment audio files
    └── chapters/            # final assembled chapter audio
```

## Dependencies

- **ollama** — local LLM inference for speaker attribution
- **edge-tts** — TTS provider (free, async)
- **pydub** — audio concatenation
- **rich** — colored CLI review output
- **typer** — CLI framework
- **ffmpeg** — system dependency required by pydub for MP3
- **ollama** — system dependency (local LLM server)
