# Slice 1 — Codex implementation brief (leaves, no cross-module deps)

You are the implementer for **Slice 1** of LNVO v2 MVP Step 1 (Prepare). Claude Code is the orchestrator and has already produced a consensus-approved plan. Your job: implement the **leaf modules** of that plan — modules with no dependencies on other prepare-stage modules — plus their unit tests, add one pyproject dep, run the test suite, and commit.

## Context

- Repo: `/Users/regiswoof/_workspace/projects/assistant`
- Working tree: clean
- Branch: `feat/lnvo-v2-prepare-step1` (do **not** switch branches)
- Plan (read this first, fully): `.omc/plans/lnvo-v2-prepare-step1.md`
- Reviews (for context only): `.omc/plans/lnvo-v2-prepare-step1.architect.md`, `.omc/plans/lnvo-v2-prepare-step1.critic.md`
- Existing contract skeleton you must NOT modify:
  - `automations/ln_voice_over_v2/common/`
  - `automations/ln_voice_over_v2/pipeline/`
  - `automations/ln_voice_over_v2/series/`
  - `automations/ln_voice_over_v2/stages/*/contracts.py` (already locked)

## Slice 1 scope (and ONLY this)

Create or update these files. Do not touch anything else under `automations/` or `src/` or `tests/` outside this list.

### New source files

1. `automations/ln_voice_over_v2/stages/prepare/prompts.py` — implement per plan §`prompts.py`. One module-level constant `OCR_PROMPT`. The prompt text must satisfy every bullet in §`prompts.py` (no fences, no prose, two-column ordering, no translation, empty transcript on full-bleed illustrations).
2. `automations/ln_voice_over_v2/stages/prepare/ocr.py` — implement per plan §`ocr.py`. Three public symbols: `OcrPageResult` (frozen Pydantic model, `extra="forbid"`, fields `transcript: str`, `is_illustration: bool`), `run_codex_ocr(...)`, `load_cached_ocr(...)`, `save_ocr(...)`. Use exactly the argv shape, subprocess flags, and error-handling described in plan §`ocr.py` line by line. **`save_ocr` and `load_cached_ocr` must replicate the atomic-write primitive locally** (`tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8")` + `tmp_path.replace(path)`) — do NOT import `common/json_io.save_json_contract`.
3. `automations/ln_voice_over_v2/stages/prepare/downloader.py` — implement per plan §`downloader.py`. One free function `download_anyflip(url, dest_pdf, *, executable="anyflip-downloader", timeout_seconds=...) -> Path`. Subprocess the external CLI; assert post-condition (zero exit, `dest_pdf` exists and non-empty). No class. No Protocol.
4. `automations/ln_voice_over_v2/stages/prepare/rasterizer.py` — implement per plan §`rasterizer.py`. Public surface includes `RasterizedPage` (Pydantic frozen, `page: int >= 1`, `image_path: Path`) and `rasterize_pdf(pdf_path, pages_dir, *, dpi=200) -> list[RasterizedPage]`. Use `pymupdf` (`import fitz`). Render via `Pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)` (RGB no-alpha). File names are 1-indexed `{page:03d}.png`. Resume semantics: if a page PNG already exists at the target path, do not rewrite it (preserves mtime); only render missing pages.
5. `automations/ln_voice_over_v2/stages/prepare/validation.py` — implement per plan §`validation.py`. Public function `validate_prepared_volume(volume: PreparedVolume, volume_root: Path) -> None`. Anchor convention pinned in the docstring (copy verbatim from §`validation.py`). Emit one `ValidationProblem` per failure with the exact `code` strings listed in the plan: `text_units_empty`, `text_unit_order_gap`, `text_unit_order_duplicate`, `text_unit_source_missing`, `media_path_missing`, `media_source_missing`, `media_order_gap`, `media_order_duplicate`. Raise `ContractValidationError(problems)` if any.

### New test files

6. `tests/automations/ln_voice_over_v2/stages/__init__.py` — empty file.
7. `tests/automations/ln_voice_over_v2/stages/prepare/__init__.py` — empty file.
8. `tests/automations/ln_voice_over_v2/stages/prepare/test_ocr_function.py` — implement per plan §`test_ocr_function.py`. All bullets. Stub `subprocess.run` via `unittest.mock.patch` — do NOT call the real `codex` CLI. Use `pytest.MonkeyPatch` or `mocker` (no new dev deps).
9. `tests/automations/ln_voice_over_v2/stages/prepare/test_downloader.py` — implement per plan §`test_downloader.py`. Stub the subprocess; test happy path, non-zero exit, missing-output-file post-condition. Do NOT call real `anyflip-downloader`.
10. `tests/automations/ln_voice_over_v2/stages/prepare/test_rasterizer.py` — implement per plan §`test_rasterizer.py`. Use a real small fixture PDF: generate it inside a `@pytest.fixture` using `pymupdf` itself (`fitz.open()` → `new_page()` → `insert_text()`) — 2 pages, simple text. Assert 1-indexed PNG file names, alpha=False (compare `Image.open(png).mode == "RGB"` via Pillow which is already a dep), resume-skip (mtime unchanged on second call).
11. `tests/automations/ln_voice_over_v2/stages/prepare/test_validation.py` — implement per plan §`test_validation.py`. Construct `PreparedVolume` instances by hand using the existing contract; use a `tmp_path` fixture to lay out real files matching the source_paths so passing-case tests work, then unlink files to trigger missing-file failures.

### pyproject.toml

12. Add `pymupdf>=1.24` to `[project].dependencies`. Append after the existing `pydantic` line. Do not touch other lines.

13. Run `uv lock` to regenerate `uv.lock` after editing `pyproject.toml`. Commit the regenerated lock alongside the dep change.

## Hard constraints

- Do NOT create `runner.py`, `__main__.py`, `media.py`, `text_units.py`, `__init__.py` updates beyond the test `__init__.py` files listed. Those belong to slices 2 and 3.
- Do NOT modify `automations/ln_voice_over_v2/AGENTS.md` or `automations/ln_voice_over_v2/README.md`. Those land in slice 3.
- Do NOT modify any file under `automations/ln_voice_over_v2/common/`, `pipeline/`, `series/`, or any `stages/*/contracts.py`.
- Do NOT introduce a new pytest plugin, mocker library, or other dev dep. Use stdlib `unittest.mock` and `pytest.MonkeyPatch`.
- Do NOT add try/except blocks except where the plan explicitly calls for them (network/I/O at boundaries).
- Use Google-style docstrings on public functions, types per plan signatures.
- Follow project lint via `ruff check .` and `ruff format .` before committing.
- Tests must NOT exercise the real `codex` CLI or the real `anyflip-downloader`. Stubs only.

## Verification (must all pass before commit)

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run pytest tests/automations/ln_voice_over_v2/ -x -q
```

If `ruff check` flags a real issue, fix it. If it flags style noise unrelated to your additions, leave it alone.

## Commit

When all four commands succeed, stage **only** the files you created or modified in this slice, then commit with:

```text
feat(lnvo-v2): add prepare-stage leaf modules and pymupdf dep

Implements Slice 1 of the approved Step 1 plan at .omc/plans/lnvo-v2-prepare-step1.md.
Adds prompts.py, ocr.py, downloader.py, rasterizer.py, validation.py and their unit
tests. Adds pymupdf as a project dependency for PDF rasterization. No runner, no CLI,
no AGENTS.md/README changes yet — those land in Slice 2 and Slice 3.
```

Do not push. Do not open a PR. Stop after the commit.

## Reply format

When you exit, your final assistant message must contain exactly:

1. The commit SHA (first 12 chars).
2. The `git diff --stat HEAD~1..HEAD` output.
3. The last 8 lines of the pytest output.
4. Any TODOs or follow-ups you noted while implementing.

Nothing else.
