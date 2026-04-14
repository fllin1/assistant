# LN Voice Over — Architecture Reference

## Pipeline

```
SPLIT → CLEAN → PARSE → ATTRIBUTE → REVIEW → SYNTHESIZE → ASSEMBLE
  │        │        │         │          │          │           │
  ▼        ▼        ▼         ▼          ▼          ▼           ▼
chapters/ cleaned/ parsed/  attributed/ reviewed/  audio/      audio/
(txt)    (txt)    (json)   (json)      (json)     segments/   chapters/
```

6 stages, each independently runnable. Each reads from the previous stage's
output directory and writes to its own. All intermediate data is inspectable.

## Runtime Data Layout

```
~/.assistant/ln_voice_over/projects/<book-slug>/
├── config/
│   ├── characters.json      # CharacterRegistry
│   └── voices.json          # VoiceConfig
├── raw/
│   └── volume.txt           # Original input
├── chapters/
│   ├── manifest.json        # Chapter metadata + pov_character
│   └── chapter_*.txt
├── cleaned/
├── parsed/                  # JSON per chapter
├── attributed/              # JSON per chapter (with speaker/confidence)
├── reviewed/                # JSON per chapter (user-approved)
├── experiments/
│   └── extraction/          # Step 1 experiment runs (config + results per batch)
├── ground_truth_*.json      # Manually verified attributions for evaluation
└── audio/
    ├── segments/            # Cached per-segment audio (<cache_key>.mp3)
    └── chapters/            # Final concatenated chapter audio
```

## Stage 1: SPLIT — Volume to Chapters

- **Input**: `raw/<book-slug>.txt`
- **Output**: `chapters/chapter_01.txt`, ..., `chapters/manifest.json`
- Detect chapter boundaries via configurable regex patterns
- `manifest.json` has `pov_character: null` — user fills it manually
- Front matter before first header → `chapter_00.txt` or skipped

## Stage 2: CLEAN — Artifact Removal

- **Input**: `chapters/*.txt` → **Output**: `cleaned/*.txt`
- Remove watermark lines, standalone page numbers
- Collapse 3+ blank lines to 2
- Preserve scene breaks (`***`, `---`, `* * *`, etc.)
- Normalize encoding to UTF-8

## Stage 3: PARSE — Structural Segmentation

- **Input**: `cleaned/*.txt` → **Output**: `parsed/chapter_01.json`
- Segment types: `narration`, `dialogue`, `inner_thought`, `scene_break`, `chapter_header`
- Split at paragraph boundaries; each dialogue block = one segment
- **No mid-sentence splitting**: `She said "hello" and walked away.` stays as one `narration` segment
- Long narration (>500 chars) split at sentence boundaries

## Stage 4: ATTRIBUTE — Speaker Attribution

Two-step pipeline using local LLMs (Ollama).

### Step 1: Mention Extraction (`extraction.py`)

- **Input**: `parsed/*.json` → **Output**: experiment results in `experiments/extraction/`
- Per-dialogue LLM calls with ±5 context segments
- LLM extracts: `raw_mention` (name/pronoun from narration), `resolved_mention` (best guess), `mention_source_index`, `mention_type`, `reasoning`
- Cross-validated with two models (gemma4:26b, qwen3.5:27b); disagreements flagged for verification
- Versioned prompts in `prompts/extraction_v*.txt`
- Experiment framework: batch runner, ground truth comparison, results persistence

### Step 2: Entity Resolution (planned)

- **Input**: extraction results + `config/characters.json` → **Output**: `attributed/*.json`
- Maps `resolved_mention` to canonical registry names
- Names → regex/alias lookup; pronouns/ambiguous → AI resolution

### Legacy Attribution (`attribute.py`)

- Windowed and per-dialogue LLM attribution (direct speaker assignment)
- `narration` → `pov_character` if set, else `NARRATOR`
- `dialogue` / `inner_thought` → LLM-attributed with registry validation
- Still functional but being replaced by the two-step pipeline

## Stage 5: REVIEW — Manual Correction

- **Input**: `attributed/*.json` → **Output**: `reviewed/*.json`
- CLI interactive: color-coded segments, low-confidence highlighted
- Direct JSON editing supported
- `--approve-all` to skip review

## Stage 6: SYNTHESIZE + ASSEMBLE

- **Input**: `reviewed/*.json` + `config/voices.json` → **Output**: `audio/chapters/*.mp3`

### Voice Resolution

```
scene_break     → silence (no TTS)
chapter_header  → NARRATOR voice
narration       → pov_character voice if set, else NARRATOR
dialogue/thought → speaker's mapped voice → gender default → NARRATOR
```

### Caching

`cache_key = sha256(f"{voice_id}:{text}")[:16]` — content-addressable.
Re-runs after fixing one attribution only re-synthesize changed segments.

### Assembly

Concatenate with `pydub`, insert silence between segments:
- 200ms dialogue→dialogue
- 400ms narration↔dialogue
- 800ms scene break
- 1500ms chapter header

## Dependencies

```
edge-tts        # TTS provider (free, async)
pydub           # Audio concatenation
ollama          # LLM attribution via local Ollama models
rich            # Colored CLI review output
typer           # CLI framework
```

System: `ffmpeg` (required by pydub for MP3), `ollama` (local LLM server).
