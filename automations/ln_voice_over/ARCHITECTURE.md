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

## Stage 4: ATTRIBUTE — LLM Speaker Attribution

- **Input**: `parsed/*.json` + `config/characters.json` → **Output**: `attributed/*.json`
- `narration` → `pov_character` if set, else `NARRATOR`
- `dialogue` / `inner_thought` → LLM-attributed
- **Windowing**: scenes split at `scene_break`, windows of ~40 segments with ~8 overlap
- LLM via OpenRouter; model configurable

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
openai          # LLM attribution via OpenRouter
rich            # Colored CLI review output
```

System: `ffmpeg` (required by pydub for MP3).
