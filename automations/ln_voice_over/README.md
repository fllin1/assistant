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
| **Attribute** | Use an LLM (via OpenRouter) to assign speakers to dialogue and thought segments |
| **Review** | Interactive CLI for reviewing and correcting speaker attributions |
| **Synthesize** | TTS synthesis per segment with per-character voices, then assemble into chapter audio files |

## CLI Commands

The CLI is available as the `lnvo` command (registered in `pyproject.toml`).

```bash
# Project setup
lnvo init                          # create a new project or select an existing one

# Run individual stages
lnvo split <book-slug>             # stage 1: volume → chapters
lnvo clean <book-slug>             # stage 2: remove artifacts
lnvo parse <book-slug>             # stage 3: text → typed segments
lnvo attribute <book-slug>         # stage 4: LLM speaker attribution
lnvo attribute <book-slug> --chapter 3   # single chapter
lnvo review <book-slug>            # stage 5: interactive review
lnvo review <book-slug> --approve-all    # auto-approve all
lnvo synthesize <book-slug>        # stage 6: TTS + audio assembly
lnvo synthesize <book-slug> --chapter 5  # single chapter

# Full pipeline
lnvo run-all <book-slug>                   # run all stages
lnvo run-all <book-slug> --from-stage parse  # resume from a stage
```

## Getting Started

1. Run `lnvo init` to create a project (e.g., "mushoku-tensei-vol-1").
2. Place your `.txt` volume file in `~/.assistant/ln_voice_over/projects/<slug>/raw/`.
3. Edit `config/characters.json` with the book's characters (names, aliases, gender).
4. Run the pipeline stage by stage, or use `lnvo run-all <slug>`.
5. Review attributions at the review stage, then synthesize.

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
└── audio/
    ├── segments/            # cached per-segment audio files
    └── chapters/            # final assembled chapter audio
```

## Dependencies

- **edge-tts** — TTS provider (free, async)
- **pydub** — audio concatenation
- **openai** — LLM attribution via OpenRouter
- **rich** — colored CLI review output
- **ffmpeg** — system dependency required by pydub for MP3
