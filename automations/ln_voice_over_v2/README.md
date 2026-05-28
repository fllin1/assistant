# LN Voice Over V2

LNVO v2 is the contract-first architecture for turning a light novel volume into
audio-first, visual-supported media.

This package currently contains only the skeleton contracts and validators for
the target pipeline:

```text
prepare -> transform -> dialogue -> scenes -> generation
```

It does not implement OCR, parsing, attribution prompts, TTS, video rendering,
CLI commands, or data-porting tools.

Runtime data is stored outside the repository. Repository files define public
contracts, validation rules, path conventions, and tests.

### Prepare stage (Step 1)

**Runtime prerequisites (not installed by `pyproject.toml`):**

- `anyflip-downloader` on `PATH` (install per the upstream project's instructions; the LNVO v2 runner only shells out to it).
- `codex` CLI on `PATH`, and the user must have signed in once via `codex login` using their ChatGPT subscription. The runner does not handle auth.
- The default OCR model id is `gpt-5.5` — the model the Codex CLI exposes for ChatGPT-account auth. If your `codex` CLI rejects that id, every page will fail uniformly during the first run — pass `--ocr-model <name>` to switch to a model the CLI accepts (e.g. probe with `printf hi | codex exec -m <name> -s read-only --skip-git-repo-check`).

**CLI usage:**

```bash
python -m automations.ln_voice_over_v2.stages.prepare \
    --url "https://anyflip.com/<flipbook-url>" \
    --series classroom-of-the-elite-year-2 \
    --volume v4
```

Optional flags: `--story-profile <slug>` (defaults to `<series>`), `--data-root <path>` (defaults to `~/.assistant/ln_voice_over_v2/projects`), `--workers <int>` (default 4), `--ocr-model <name>` (default `gpt-5.5`), `--force`, `--force-ocr`.

**Expected runtime layout (under `~/.assistant/ln_voice_over_v2/projects/<series>/<volume>/`):**

```
source/
  volume.pdf
  pages/{page:03d}.png          # 1-indexed filesystem pages
  ocr/{page:03d}.json           # strict {"transcript": str, "is_illustration": bool}
prepared/
  volume.json                   # PreparedVolume artifact
  media/illustration-{seq:03d}.png
```

**Path-anchor legend:** every `ArtifactPath` embedded in `prepared/volume.json` (`text_unit.source_path`, `media.path`, `media.source_path`) is POSIX-relative to **the volume root** (the directory shown above), not relative to `prepared/`. Downstream stages resolve absolute paths as `volume_root / artifact_path`.

**Page-index legend:** filesystem page filenames and the `page` value in `source_locator` are **1-indexed**. `PreparedTextUnit.order`, the integer suffix of `text_unit_id`, and `PreparedMedia.order` are **0-indexed**.

**Re-run flags:**

- (no flag) per-page resume — keeps any `source/ocr/{page:03d}.json` that already parses via `OcrPageResult.model_validate_json(...)` (strict, `extra="forbid"`); recomputes the rest. A cache file that exists but fails strict parse is logged at `WARNING` and recomputed (it is not treated as authoritative). `prepared/media/` is left alone unless an `is_illustration` verdict changes on this run.
- `--force-ocr` — recompute every page's OCR; reuse `source/volume.pdf` and `source/pages/*.png` if present. Rebuilds `prepared/media/` from the new OCR pass: stale `illustration-*.png` files for pages no longer flagged as `is_illustration` are deleted before the new set is copied in.
- `--force` — wipe `source/ocr/`, `prepared/`, and re-rasterize all pages; the PDF is still reused if already on disk. Rebuilds `prepared/media/` the same way as `--force-ocr`.
- **Precedence**: `--force` and `--force-ocr` are mutually exclusive at the CLI; passing both is a usage error (argparse rejects it before the runner is invoked). `--force` already implies recomputing OCR, so the combined form is rejected rather than allowed-with-precedence to keep behavior explicit.

If `gpt-5.5` refuses to OCR a page, the runner retries up to three times with escalating prompt variants. Pages that exhaust the retry budget receive a sentinel empty-transcript `PreparedTextUnit` flagged `needs_review: true`, and the run completes without manual intervention.

**Run the prepare-stage tests:**

```bash
pytest tests/automations/ln_voice_over_v2/stages/prepare/
```

### Transform stage (Step 2)

**Runtime prerequisites:** none beyond the prepared volume from Stage 1. The stage is deterministic and code-only: no LLM, OCR, network, or subprocess.

**CLI usage:**

```bash
python -m automations.ln_voice_over_v2.stages.transform \
    --series classroom-of-the-elite-year-2 \
    --volume v4
```

Optional flags: `--data-root <path>` (defaults to `~/.assistant/ln_voice_over_v2/projects`), `--story-profile <slug>` (reserved; not yet consumed by the resolver), `--force`.

**Expected runtime layout (under `~/.assistant/ln_voice_over_v2/projects/<series>/<volume>/`):**

```text
volume_index.json
segments/
  chapter_01.json
  chapter_02.json
  ...
```

**Story-profile resolution:** `<data_root>/<series>/config/story_profile.json` wins when present; otherwise the packaged template `automations/ln_voice_over_v2/series/templates/story_profile.default.json` is used. The runner logs the resolved file at `INFO` so re-runs can be replicated.

**Re-run flags:**

- (no flag) overwrites `volume_index.json` and individual `segments/<chapter_id>.json` files atomically via the same temp-file replace pattern as Stage 1. Stale `chapter_NN.json` files for chapters that no longer exist in this run are not removed without `--force`.
- `--force` — `shutil.rmtree(segments/, ignore_errors=True)` and `volume_index.json.unlink(missing_ok=True)` before writing the new artifacts. Use when the chapter set has shrunk between runs.

The stage-local and cross-artifact validators (`pipeline.validators.validate_transform_against_prepared`) run before the runner writes any file. A validation failure therefore leaves existing `volume_index.json` and `segments/*.json` untouched.

**Run the transform-stage tests:**

```bash
pytest tests/automations/ln_voice_over_v2/stages/transform/
```
