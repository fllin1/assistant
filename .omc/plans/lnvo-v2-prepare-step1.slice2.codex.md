# Slice 2 — Codex implementation brief (text_units + media + tests)

You are implementing **Slice 2** of LNVO v2 MVP Step 1 (Prepare). Slice 1 already landed at commit `b16b9a9` on branch `feat/lnvo-v2-prepare-step1`. Your job: implement the **composition helpers** that depend on Slice 1's leaf modules, plus their unit tests. The orchestrator (Claude Code) runs lint / pytest / commit after you finish — do **not** attempt those yourself; you already learned the sandbox blocks them.

## Context

- Repo: `/Users/regiswoof/_workspace/projects/assistant`
- Branch: `feat/lnvo-v2-prepare-step1` (do not switch)
- Plan (read fully): `.omc/plans/lnvo-v2-prepare-step1.md`
- Slice 1 brief (for context): `.omc/plans/lnvo-v2-prepare-step1.slice1.codex.md`
- Existing files you must NOT modify:
  - anything under `automations/ln_voice_over_v2/common/`, `pipeline/`, `series/`
  - any `stages/*/contracts.py` (locked contract skeleton)
  - the 5 Slice 1 source modules (`prompts.py`, `ocr.py`, `downloader.py`, `rasterizer.py`, `validation.py`) — they are frozen for this slice
  - any Slice 1 test file — frozen for this slice
  - `pyproject.toml`, `uv.lock`, `AGENTS.md`, `README.md` — out of scope

## Important: Slice 1 deviation already in tree

`RasterizedPage` (in `automations/ln_voice_over_v2/stages/prepare/rasterizer.py`) is a **Pydantic `BaseModel`** (frozen, `extra="forbid"`) with fields `page: int >= 1` and `path: Path` — not a `@dataclass`. The plan's `§rasterizer.py` snippet wrote `@dataclass(frozen=True)` and `path: Path`; the in-tree code matches the plan's field name (`path`) but uses Pydantic for codebase consistency. Build all Slice 2 code against the **actual in-tree class**, not the plan's snippet — read `automations/ln_voice_over_v2/stages/prepare/rasterizer.py` directly to confirm.

`OcrPageResult` (in `automations/ln_voice_over_v2/stages/prepare/ocr.py`) is a Pydantic `BaseModel` (frozen, `extra="forbid"`) with fields `transcript: str` and `is_illustration: bool`. Build against that.

## Slice 2 scope (and ONLY this)

### New source files

1. `automations/ln_voice_over_v2/stages/prepare/text_units.py` — implement per plan §`text_units.py`. One public function `build_text_units(ocr_results: list[OcrPageResult], rasterized: list[RasterizedPage]) -> tuple[PreparedTextUnit, ...]`. Page-index convention exactly as the plan describes: emit one `PreparedTextUnit` per `(page, OcrPageResult)` pair where `page` is the 1-indexed filesystem page number from `rasterized[i].page`. The text unit's id is `f"unit_{page-1:06d}"`, `order = page - 1`, `text = ocr.transcript`, `source_path = f"source/pages/{page:03d}.png"`, `source_locator = {"page": page}`. Assert `len(ocr_results) == len(rasterized)` at call entry and that the two lists are in matching 1-indexed page order (caller's responsibility; you may add an `assert` to make this loud). Illustration-only pages still emit a unit with `text == ""` so `order` stays contiguous.

2. `automations/ln_voice_over_v2/stages/prepare/media.py` — implement per plan §`media.py`. One public function:
   ```python
   def collect_media(
       ocr_results: list[OcrPageResult],
       rasterized: list[RasterizedPage],
       volume_root: Path,
       *,
       rebuild: bool = False,
   ) -> tuple[PreparedMedia, ...]:
   ```
   - Assert `len(ocr_results) == len(rasterized)` and matching 1-indexed page order.
   - The `prepared/media/` directory is `volume_root / "prepared" / "media"`. Create it if missing.
   - When `rebuild=True`, delete every existing file under `prepared/media/` (unlink files; do not blow away the dir) **before** copying the new set.
   - When `rebuild=False`, leave existing files alone.
   - For each `(rasterized_page, ocr_result)` pair with `ocr_result.is_illustration == True`, allocate a sequential `seq` starting at 1 across illustrations only, and copy `rasterized_page.path` → `volume_root / "prepared" / "media" / f"illustration-{seq:03d}.png"` using `shutil.copyfile`. Emit `PreparedMedia(media_id=f"illustration-{seq:03d}", order=seq-1, media_type=MediaType.ILLUSTRATION, path=f"prepared/media/illustration-{seq:03d}.png", source_path=f"source/pages/{rasterized_page.page:03d}.png")`.
   - Return `tuple(...)` of `PreparedMedia` in `seq` order.

### New test files

3. `tests/automations/ln_voice_over_v2/stages/prepare/test_text_units.py` — implement per plan §`test_text_units.py`:
   - Given N matched pages, `build_text_units` emits N units with `order` contiguous from 0 and ids `unit_000000`, `unit_000001`, … through `unit_{N-1:06d}`.
   - `source_locator["page"]` equals the 1-indexed filesystem page number.
   - Illustration-only pages still emit a unit (with `text == ""`) so `order` stays contiguous.
   - The integer suffix of `text_unit_id` (zero-padded 6 digits) equals `order` (zero-indexed).
   - `source_path` is exactly `f"source/pages/{page:03d}.png"`.
   - Use `pytest.MonkeyPatch` and real Pydantic instances built from the in-tree `OcrPageResult` / `RasterizedPage` / `PreparedTextUnit`. No mocks for these — they are cheap to construct.

4. `tests/automations/ln_voice_over_v2/stages/prepare/test_media.py` — implement per plan §`test_media.py`:
   - Only pages with `is_illustration=True` produce media entries.
   - `seq` numbering is 1-based and contiguous across illustrations only.
   - The illustration PNGs are copied to `prepared/media/illustration-{seq:03d}.png` under the `tmp_path` volume root, and the copied bytes equal the source page bytes.
   - `order == seq - 1` for every emitted `PreparedMedia`.
   - `rebuild=True` deletes any pre-existing files under `prepared/media/` before copying the new set — write a leftover `illustration-013.png` before the call and assert it's gone after.
   - `rebuild=False` leaves pre-existing files under `prepared/media/` alone for pages not currently illustrations — write a leftover file, call with `rebuild=False`, assert the leftover is still on disk after.
   - Use `tmp_path` for the volume root. Construct `RasterizedPage` and `OcrPageResult` instances directly. Use small real PNG bytes (e.g., `b"\x89PNG\r\n\x1a\n" + b"\x00" * 16`) — no need for a real renderer.

## Hard constraints

- Do NOT create `runner.py`, `__main__.py`, or modify `stages/prepare/__init__.py`. Those belong to Slice 3.
- Do NOT touch any file outside the two source files and two test files listed above.
- Do NOT introduce new dependencies. Use stdlib `shutil`, `pathlib`.
- Use Google-style docstrings on public functions.
- Do NOT add try/except blocks; let errors propagate.
- Follow project lint conventions (the orchestrator will run `ruff check` and `ruff format` after you finish).
- Tests must be self-contained: do NOT exercise the real `codex` CLI, real `anyflip-downloader`, or real PDF rasterization. Construct the in-memory Pydantic instances directly.

## Reply format

When you exit, your final assistant message must contain exactly:

1. The list of files you created (paths, one per line).
2. The signatures of the two public functions you wrote (one line each).
3. Any deviations you took from this brief or from the plan, with one-sentence justifications.
4. Any TODOs or follow-ups you noted.

Do not run `git`, `uv`, `pytest`, `ruff`, or `pip`. The orchestrator handles those.
