# Slice 3 — Codex implementation brief (runner + CLI + AGENTS.md + README + integration tests)

You are implementing the final slice of LNVO v2 MVP Step 1 (Prepare). Slices 1 (`b16b9a9`) and 2 (`707ed82`) are already on branch `feat/lnvo-v2-prepare-step1`. This slice wires the orchestrator, the `python -m`-style CLI, widens the package AGENTS.md, expands the package README, and adds the two integration test files. The orchestrator (Claude Code) handles `uv sync`, lint, pytest, and the commit — do **not** attempt those yourself.

## Context

- Repo: `/Users/regiswoof/_workspace/projects/assistant`
- Branch: `feat/lnvo-v2-prepare-step1` (do not switch)
- Plan (read fully): `.omc/plans/lnvo-v2-prepare-step1.md`
- Slice 1 / Slice 2 briefs for context: `.omc/plans/lnvo-v2-prepare-step1.slice1.codex.md`, `.omc/plans/lnvo-v2-prepare-step1.slice2.codex.md`
- In-tree files you must build against and NOT modify:
  - `automations/ln_voice_over_v2/stages/prepare/prompts.py` (OCR_PROMPT)
  - `automations/ln_voice_over_v2/stages/prepare/ocr.py` (`OcrPageResult`, `run_codex_ocr`, `load_cached_ocr`, `save_ocr`)
  - `automations/ln_voice_over_v2/stages/prepare/downloader.py` (`download_anyflip`)
  - `automations/ln_voice_over_v2/stages/prepare/rasterizer.py` (`RasterizedPage` is a **Pydantic BaseModel** with field name `path`, not `image_path`; `rasterize_pdf(..., dpi=200, force=False)`)
  - `automations/ln_voice_over_v2/stages/prepare/validation.py` (`validate_prepared_volume`)
  - `automations/ln_voice_over_v2/stages/prepare/text_units.py` (`build_text_units`)
  - `automations/ln_voice_over_v2/stages/prepare/media.py` (`collect_media(..., rebuild=False)`)
  - all of `automations/ln_voice_over_v2/common/`, `pipeline/`, `series/`, `stages/*/contracts.py`
  - `pyproject.toml`, `uv.lock`

## Slice 3 scope

### A. New source file: `automations/ln_voice_over_v2/stages/prepare/runner.py`

Implement per plan §`runner.py` (lines 155-208 of the plan). Highlights — follow the plan line-by-line, this is just a reminder:

- Module-level constant `SOURCE_PROFILE: Final[str] = "pdf-llm-ocr"`. Set unconditionally on every emitted `PreparedVolume.source_profile`.
- `@dataclass(frozen=True) class PrepareConfig(...)` per plan signature (anyflip_url, series, volume, data_root=DEFAULT_PROJECT_DATA_ROOT, story_profile=None, ocr_model="gpt-5-mini", workers=4, force=False, force_ocr=False).
- `@dataclass(frozen=True) class PrepareResult(...)` per plan signature (prepared_volume_path, prepared_volume, page_count, illustration_count).
- `def run_prepare(config: PrepareConfig, *, download_fn=None, ocr_fn=None) -> PrepareResult` per plan signature. The two callable kwargs are the test-injection seams; when both are `None`, build them with `functools.partial` over `download_anyflip` and `run_codex_ocr` exactly as the plan describes.
- Use `paths.volume_root(config.data_root, config.series, config.volume)`, `paths.prepared_volume_path(...)`, and explicit string joins for `source/volume.pdf`, `source/pages/`, `source/ocr/`. Do NOT recompute these path conventions; the existing `automations/ln_voice_over_v2/common/paths.py` is the only authority.
- Concurrency primitive: `concurrent.futures.ThreadPoolExecutor(max_workers=config.workers)`. Each per-page worker performs the cache → OCR → save → return sequence in plan §runner.py step 200-206. The per-page `save_ocr(cache_path, result)` MUST happen **before** the worker returns so partial progress is durable.
- Malformed cache handling: `path.exists()` is True but `load_cached_ocr(path)` returns `None` → emit `logger.warning("source/ocr/%03d.json failed strict parse; recomputing", page)` and fall through to OCR. Use `logger = logging.getLogger("ln_voice_over_v2.prepare")` at module top.
- `--force` recomputes everything: rasterize with `force=True`, skip cache, rebuild media.
- `--force-ocr` recomputes OCR only: rasterize with `force=False`, skip cache, rebuild media (`collect_media(..., rebuild=True)`).
- Default (neither flag): rasterize with `force=False`, honor cache, `collect_media(..., rebuild=False)`.
- Before writing `prepared/volume.json`, call `validate_prepared_volume(prepared, volume_root)`. On `ContractValidationError`, let it propagate.
- Persist via `automations.ln_voice_over_v2.common.json_io.save_json_contract(prepared_volume_path, prepared)`. `PreparedVolume` IS a `PersistedArtifact`, so the shared helper applies (unlike `OcrPageResult`, which uses the local atomic-write primitive).
- Story-profile default: `prepared.story_profile = config.story_profile if config.story_profile is not None else config.series` (per `ProfileId` slug regex; the `series` slug must itself satisfy `ProfileId` — it does because `ProfileId` and `SeriesId` are both `SlugId`).
- Sorting: sort `rasterized` and `ocr_results` by 1-indexed page number ascending before calling `build_text_units` / `collect_media`.
- Return `PrepareResult(prepared_volume_path=..., prepared_volume=prepared, page_count=len(prepared.text_units), illustration_count=len(prepared.media))`.

### B. New source file: `automations/ln_voice_over_v2/stages/prepare/__main__.py`

Implement per plan §`__main__.py` (lines 146-153):

- `def main(argv: list[str] | None = None) -> int`.
- argparse with: `--url` (required), `--series` (required), `--volume` (required), `--story-profile`, `--data-root`, `--workers` (int, default 4), `--ocr-model` (default `"gpt-5-mini"`), `--force` and `--force-ocr` in an `add_mutually_exclusive_group()`.
- Configure root logger with a stderr handler at `INFO` level (so the runner's warnings/info surface).
- Build a `PrepareConfig` from the parsed args (let Pydantic / dataclass constructors do their validation; do NOT pre-validate the slug regexes in argparse).
- Call `run_prepare(config)`. On success, print the prepared volume path to stdout and return 0. On `ContractValidationError`, print each `problem.code: problem.path: problem.message` to stderr and return 2. On any other exception, print the message to stderr and return 1.
- `if __name__ == "__main__": raise SystemExit(main())`.

### C. Update `automations/ln_voice_over_v2/stages/prepare/__init__.py`

Re-export the public surface so importers can do `from automations.ln_voice_over_v2.stages.prepare import run_prepare, PrepareConfig, PrepareResult`:

```python
"""Prepare stage public surface."""

from .contracts import PreparedMedia, PreparedTextUnit, PreparedVolume
from .downloader import download_anyflip
from .ocr import OcrPageResult, load_cached_ocr, run_codex_ocr, save_ocr
from .runner import SOURCE_PROFILE, PrepareConfig, PrepareResult, run_prepare

__all__ = [
    "OcrPageResult",
    "PrepareConfig",
    "PrepareResult",
    "PreparedMedia",
    "PreparedTextUnit",
    "PreparedVolume",
    "SOURCE_PROFILE",
    "download_anyflip",
    "load_cached_ocr",
    "run_codex_ocr",
    "run_prepare",
    "save_ocr",
]
```

(Adjust slot order to satisfy ruff `isort` if needed.)

### D. Edit `automations/ln_voice_over_v2/AGENTS.md`

Per plan §"AGENTS.md scope change". The current "Boundaries" bullet 3 reads:

```
- Do not add CLI commands, OCR, parsing algorithms, LLM prompts, TTS rendering,
  visual rendering, data-porting logic, or plugin frameworks here.
```

**Replace that single bullet with these two bullets, verbatim:**

```
- Stages other than `stages/prepare/` remain contract-only. Do not add CLI
  commands, OCR, parsing algorithms, LLM prompts, TTS rendering, visual
  rendering, data-porting logic, or plugin frameworks in `stages/transform/`,
  `stages/dialogue/`, `stages/scenes/`, `stages/generation/`, or anywhere
  under `common/`, `pipeline/`, or `series/`.
- `stages/prepare/` may add a runner, a `python -m`-style CLI, PDF
  rasterization, one OCR prompt string, and plain module-level seam
  functions (`run_codex_ocr`, `download_anyflip`) that subprocess external
  CLIs. These seams are kept as free functions injected via `Callable`
  keywords, **not** as Protocols/ports/adapters, so the "Code Rules" bullet
  on empty ports remains satisfied. New external runtime dependencies must
  be installable via PyPI (e.g. `pymupdf`) or documented in the package
  README (e.g. `anyflip-downloader`, `codex`). No vendoring.
```

The "Code Rules" section is unchanged — do not touch it.

### E. Edit `automations/ln_voice_over_v2/README.md`

Append the "Prepare stage (Step 1)" section per plan §"README updates" (lines 396-444). Copy that block verbatim, including:

- Runtime prerequisites
- CLI usage example
- Expected runtime layout
- Path-anchor legend
- Page-index legend
- Re-run flags
- Pytest invocation line

Do not modify pre-existing README content; only append.

### F. New test file: `tests/automations/ln_voice_over_v2/stages/prepare/test_runner_resume.py`

Implement per plan §`test_runner_resume.py` (lines 502-509). All bullets:

- Pre-existing valid `source/ocr/{page:03d}.json` is reused (injected `ocr_fn` is asserted NOT called for that page).
- Pre-existing **invalid** `source/ocr/{page:03d}.json` triggers exactly one `logging.WARNING` per offending page (captured via `caplog`) and the `ocr_fn` IS called for that page.
- `--force` causes recomputation of OCR AND re-rasterization (assert both fakes called every page) and rebuilds `prepared/media/`.
- `--force-ocr` causes OCR recomputation only; pre-existing page rasters are reused; `prepared/media/` is rebuilt.
- **Mutual exclusion**: `main(["--url", "...", "--series", "s", "--volume", "v", "--force", "--force-ocr"])` returns a non-zero exit and does not call the runner (argparse usage error).
- **Partial-progress test**: a `fake_ocr_fn` returns success for page 1 and raises for page 2; run with `workers=2`. After the exception aborts the run, assert `source/ocr/001.json` exists on disk and parses to a valid `OcrPageResult`; assert `source/ocr/002.json` does NOT exist. Then re-run with no flags and a fake that succeeds for page 2; assert page 1's `ocr_fn` is NOT called the second time (cache hit) and the run completes.
- **Rasterize-without-OCR resume**: pre-populate `source/pages/*.png` for every page but leave `source/ocr/` empty. Run with no flags. Assert `rasterize_pdf` is invoked but performs no writes (mtimes unchanged on page PNGs), `ocr_fn` is called once per page, and the resulting `PreparedVolume` is complete.

Inject `download_fn` and `ocr_fn` as test callables; never invoke the real `codex` CLI or `anyflip-downloader`. Use `tmp_path` for `data_root`. For the rasterizer, you can either monkey-patch `rasterize_pdf` inside `runner` OR pre-populate page PNGs and rely on `force=False` skip — the second is closer to the runtime behavior and is encouraged. For the `--force` rerasterize assertion, monkey-patching is fine.

### G. New test file: `tests/automations/ln_voice_over_v2/stages/prepare/test_runner_end_to_end.py`

Implement per plan §`test_runner_end_to_end.py` (lines 511-518):

- Inject a `fake_download_fn` that copies a fixture PDF into `source/volume.pdf`.
- Inject a `fake_ocr_fn` returning canned results (e.g. page 1 prose, page 2 illustration). Generate the fixture PDF in a fixture (use `pymupdf` directly to create 2 pages).
- Assert `run_prepare` returns a `PrepareResult` whose `prepared_volume_path` exists and the file round-trips to an equal `PreparedVolume` model.
- Assert `prepared.source_profile == "pdf-llm-ocr"` (unconditional invariant).
- Assert `prepared.story_profile == prepared.series` when the config's `story_profile` is `None`; assert it equals the explicit value when provided.
- Assert `len(prepared.text_units) == fixture_page_count` and `result.page_count == len(prepared.text_units)`.
- Assert `len(prepared.media)` equals the number of illustration pages in the fixture (1 in the example above).
- **Anchor-convention end-to-end assertion**: for every `unit` in `prepared.text_units`, assert `(volume_root / unit.source_path).is_file()`. For every `media` in `prepared.media`, assert `(volume_root / media.path).is_file()` and `(volume_root / media.source_path).is_file()`.

## Hard constraints

- Do NOT modify any file under `common/`, `pipeline/`, `series/`, or any other `stages/*/contracts.py`.
- Do NOT modify any Slice 1 or Slice 2 file.
- Do NOT add new dependencies. Use stdlib `argparse`, `logging`, `dataclasses`, `concurrent.futures`, `functools`, `shutil`, `pathlib`, `subprocess`.
- Use Google-style docstrings on public functions.
- Do NOT add try/except blocks; let errors propagate. The single exception is the top-level CLI `main()` which translates `ContractValidationError` (exit 2) and `Exception` (exit 1) per the CLI spec above.
- The OCR prompt cache directory `source/ocr/` must be created with `parent.mkdir(parents=True, exist_ok=True)` before any worker writes there.
- Tests must NOT touch the real `codex` CLI, real `anyflip-downloader`, or any network resource.

## Reply format

When you exit, your final assistant message must contain:

1. The list of files you created or modified (paths, one per line, with `[new]` or `[modified]` tag).
2. The top of `runner.py`: the module docstring, the SOURCE_PROFILE constant, and the two dataclass signatures.
3. The argparse arguments declared in `__main__.py` (one line each).
4. The exact text of the new AGENTS.md "Boundaries" bullets.
5. Any deviations from the plan or this brief, with one-sentence justifications.
6. Any TODOs or follow-ups.

Do not run `git`, `uv`, `pytest`, or `ruff`. The orchestrator handles those.
