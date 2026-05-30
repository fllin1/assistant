Runbook collects the commands that produce real artifacts at each functional stage of the LNVO v2 pipeline.

Run them in order; each stage reads what the previous stage wrote.

Stages 1, 2, and 3 (dialogue) are runnable today. Stages 4 (scenes) and 5 (generation) are not yet wired — contracts exist but no runner.

## Defaults

- Data root: `~/.assistant/ln_voice_over_v2/projects` (override with `--data-root <path>`).
- Volume artifacts live at `<data_root>/<series>/<volume>/`.
- Per-series config (optional) lives at `<data_root>/<series>/config/story_profile.json`.

## Stage 1 — prepare

Downloads the source PDF, rasterises pages, runs Codex-OCR per page, and writes a `PreparedVolume` artifact.

Runtime prerequisites:

- `anyflip-downloader` on `PATH`.
- `codex` CLI on `PATH` and signed in via `codex login`.

Canonical invocation:

```bash
python -m automations.ln_voice_over_v2.stages.prepare \
    --url "https://anyflip.com/<flipbook-url>" \
    --series classroom-of-the-elite-year-2 \
    --volume v4
```

Re-run flags:

- (no flag) — per-page resume; recompute only pages whose OCR cache is missing or fails strict parse.
- `--force-ocr` — recompute every page's OCR; keep the source PDF and page PNGs.
- `--force` — wipe `source/ocr/` and `prepared/`, re-rasterise everything. The PDF is still reused if already on disk.

Outputs:

```text
~/.assistant/ln_voice_over_v2/projects/<series>/<volume>/
├── source/
│   ├── volume.pdf
│   ├── pages/{page:03d}.png
│   └── ocr/{page:03d}.json
└── prepared/
    ├── volume.json                       # PreparedVolume artifact
    └── media/illustration-{seq:03d}.png
```

Smoke-test the stage locally without touching real data:

```bash
pytest tests/automations/ln_voice_over_v2/stages/prepare/ -q
```

## Stage 2 — transform

Reads the prepared volume, resolves a story profile, detects chapters, emits stable segments, and writes the chapter index plus per-chapter segment files. Deterministic and code-only — no LLM, OCR, network, or subprocess.

Prerequisite: Stage 1 has produced `prepared/volume.json` for the same `<series>/<volume>`.

Canonical invocation:

```bash
python -m automations.ln_voice_over_v2.stages.transform \
    --series classroom-of-the-elite-year-2 \
    --volume v4
```

Flag:

- `--force` — wipe `segments/` and `volume_index.json` before writing. Use when the chapter set has shrunk between runs.

Outputs:

```text
~/.assistant/ln_voice_over_v2/projects/<series>/<volume>/
├── volume_index.json
└── segments/
    ├── chapter_00.json     # e.g. Prologue
    ├── chapter_01.json
    ├── chapter_02.json
    └── ...
```

The runner logs `transform: using story_profile <path>` at INFO so a re-run can be replicated.

Smoke-test:

```bash
pytest tests/automations/ln_voice_over_v2/stages/transform/ -q
```

### Per-series story_profile override

If the packaged template's heading regex misses your LN's heading style, drop an override at `<data_root>/<series>/config/story_profile.json`:

```bash
mkdir -p ~/.assistant/ln_voice_over_v2/projects/<series>/config
cp automations/ln_voice_over_v2/series/templates/story_profile.default.json \
   ~/.assistant/ln_voice_over_v2/projects/<series>/config/story_profile.json
# Then edit rules.chapter_headings in the copied file.
```

The override file shares the `StoryProfile` shape; only `rules.chapter_headings` (list of Python regex strings) and `rules.subchapters` (bool) are read by Stage 2 today.

## Stage 3 — dialogue

Detects spoken dialogue, assigns speakers, and resolves chapter perspective via
one or more `codex` attribution calls per chapter. The model proposes; the
runner canonicalises names and writes the artifact.

Prerequisite: Stage 2 produced `volume_index.json` + `segments/`, and
`<data_root>/<series>/config/characters.json` exists (**required, no fallback** —
canonical character names + aliases). `codex` CLI signed in.

Canonical invocation:

```bash
# whole volume (default): every chapter in volume_index.json
python -m automations.ln_voice_over_v2.stages.dialogue \
    --series classroom-of-the-elite-year-2 \
    --volume v4 \
    --workers 4 \
    --timeout 600 \
    --max-candidates-per-chunk 300

# single chapter
python -m automations.ln_voice_over_v2.stages.dialogue \
    --series classroom-of-the-elite-year-2 \
    --volume v4 \
    --chapter chapter_01 \
    --timeout 600 \
    --max-candidates-per-chunk 300
```

Notes:

- `--chapter` is optional; omit it to run every chapter, `--workers` at a time
  (default 4). Chapter ids are `chapter_01`, `chapter_07_1`, `chapter_00`
  (front matter) — not bare numbers. An unknown `--chapter` lists the valid ids.
- `--timeout SECONDS` bounds each `codex` attribution call (default 600). A long
  chunk that reports `codex dialogue timed out after <N>s` just needs a higher
  `--timeout`; a re-run re-attempts only the missing chapters.
- `--max-candidates-per-chunk N` chunks a chapter whose candidate count exceeds
  the integer cap (default 300). Each chunk is a separate `codex` call and the
  partial proposals are merged before assembly.
- Existing `dialogue/<chapter>.json` files are **skipped unless `--force`** (the
  file is the working review surface; a re-run only fills missing chapters).
- Whole-volume mode prints per-chapter lines + a `written / skipped / failed`
  summary and exits 1 if any chapter failed; per-chapter failures are isolated.

Outputs:

```text
~/.assistant/ln_voice_over_v2/projects/<series>/<volume>/
└── dialogue/
    ├── chapter_00.json
    ├── chapter_01.json
    └── ...
```

See `docs/lnvo/03-dialogue.md` for the contract, review semantics
(`status` / `review_required` / `rejected_candidates` reasons), and the
"Debugging & Known Issues" section.

Smoke-test:

```bash
pytest tests/automations/ln_voice_over_v2/stages/dialogue/ -q
```

## Stages 4-5

Not yet implemented. The contracts live at
`automations/ln_voice_over_v2/stages/{scenes,generation}/contracts.py`. Adding a
runner is the next pipeline slice.
