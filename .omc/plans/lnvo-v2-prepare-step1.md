# LNVO v2 — Step 1 (Prepare) — Implementation Plan

Status: approved (2026-05-25, ralplan consensus: Planner + Architect APPROVE + Critic APPROVE, iteration 2)

This plan delivers the **Prepare** stage of LNVO v2 end-to-end for a single AnyFlip URL. It turns `(anyflip_url, series, volume)` into a strictly-validated `PreparedVolume` artifact at `~/.assistant/ln_voice_over_v2/projects/<series>/<volume>/prepared/volume.json` plus its on-disk sidecars (`source/volume.pdf`, `source/pages/*.png`, `source/ocr/*.json`, `prepared/media/illustration-*.png`). It exposes two replaceable stage-local seams as plain module-level `Callable`s (`run_codex_ocr`, `download_anyflip`) so we comply with the AGENTS.md "no empty ports until needed" rule while keeping the run-time injectable for tests. OCR billing rides on the user's existing `codex login` (ChatGPT subscription) via `codex exec`. No other stage and no public contract in `common/` or `stages/*/contracts.py` is touched.

---

## RALPLAN-DR Summary

### Principles

- Existing public contracts in `common/*` and `stages/*/contracts.py` are frozen for this slice.
- Stage-local seams are plain module-level callables, not Protocols. This honors the AGENTS.md "no empty runners, ports, adapters, or services" rule until a second implementation exists.
- Re-runs are cheap: per-page artifacts on disk are reusable; the runner resumes by default; each per-page success is committed to disk before any sibling join.
- OCR cost rides on the user's existing `codex login` (ChatGPT subscription). The runner adds zero billing or auth logic.
- The contract layer (Pydantic models) is the source of truth — `prepared/volume.json` only lands if it validates and all referenced files exist under `volume_root`.
- Codex-implementer ready: concrete file names, function signatures, concurrency primitive, anchor convention, and acceptance checks all pinned in writing.

### Decision Drivers

1. Step 1 must be reproducible on a single AnyFlip URL today, on this laptop, end-to-end.
2. OCR cost must be metered through `codex exec` (ChatGPT subscription), not a paid API key.
3. The downstream Transform stage must be able to consume `prepared/volume.json` without any change once it lands; the artifact-path anchor convention must be written down so Transform doesn't guess.

### Viable Options + invalidation rationale

Each axis lists ≥2 considered options and ends with the chosen one and why the others are ruled out by locked input or by the AGENTS.md "Code Rules" bullet on empty ports.

**A. Entry-point shape**
- (A1) Pure `run_prepare(...)` function only (importable, no CLI). Ruled out: user wants a hand-run smoke test against an AnyFlip URL today — needs a CLI.
- (A2) Full Typer CLI registered as a console script in `pyproject.toml`. Ruled out: contradicts locked input #1 — entry is `python -m automations.ln_voice_over_v2.stages.prepare`, no project-script entry.
- (A3 — chosen) Pure `run_prepare(...)` function + thin `__main__.py` argparse wrapper invoked as `python -m automations.ln_voice_over_v2.stages.prepare`. Matches locked input #1.

**B. OCR backend**
- (B1) Anthropic/OpenAI API via SDK. Ruled out by locked input #4 — billing must be the ChatGPT sub.
- (B2) Local Tesseract / PaddleOCR. Ruled out: light-novel pages are dense, two-column, with furigana; classical OCR quality is insufficient. Also adds heavy native deps.
- (B3 — chosen) A plain module-level function `run_codex_ocr(page_image, *, model, executable, timeout_seconds, prompt) -> OcrPageResult` that subprocesses `codex exec -i <page>.png -m <model> --ephemeral --skip-git-repo-check -s read-only "<prompt>"`. `run_prepare` accepts an `ocr_fn: Callable[[Path], OcrPageResult] | None = None` keyword for test injection; when `None` the runner constructs a partial of `run_codex_ocr` from the `PrepareConfig`. Matches locked input #4–5 **and** keeps AGENTS.md "Code Rules" intact — no Protocol introduced.

**C. OCR seam shape: Protocol vs. Callable**
- (C1) `OcrProvider` Protocol + one default `CodexExecOcrProvider` dataclass. Ruled out: AGENTS.md "Code Rules" bullet (lines 35-36) forbids empty runners/ports/adapters/services until a later slice has *real* multi-implementation behavior. This slice has exactly one OCR implementation; out-of-scope item #4 explicitly defers a second backend. Introducing a Protocol now is the anti-pattern the package's own rules name.
- (C2 — chosen) Plain `Callable[[Path], OcrPageResult]` seam injected through a `run_prepare` keyword. Same testability, zero Protocol indirection, full AGENTS.md compliance. Same shape applied to the downloader (`Callable[[str, Path], None]`).

**D. Media scope**
- (D1) Persist every page as `page_image` media. Ruled out: the contract's `media` array is for illustrations consumed by Scenes/Generation; every-page media is redundant with `source/pages/`.
- (D2 — chosen) Only pages with `is_illustration == true` become `MediaType.ILLUSTRATION` entries copied into `prepared/media/illustration-{seq:03d}.png`. Matches locked input #7.

**E. Idempotency / re-run strategy**
- (E1) Always recompute. Ruled out: codex OCR costs real money/time per page; LN volumes have 200+ pages.
- (E2) Volume-level skip if `prepared/volume.json` exists. Ruled out: too coarse — a single failing page would force a full re-OCR.
- (E3 — chosen) Per-page resume: skip OCR for any page whose `source/ocr/{page:03d}.json` already parses to the strict `OcrPageResult` shape. Flags: `--force` (everything), `--force-ocr` (OCR only). When both are passed, the combination is rejected at the argparse layer as a usage error. Malformed-cache decision is `Literal["recompute","fail-fast"] = "recompute"` (justified in the ADR). Matches locked input #11.

**F. PDF rasterizer**
- (F1) `pdf2image` (Poppler). Ruled out: extra non-Python system dep (Poppler) on top of `anyflip-downloader`; user wants minimal toolchain.
- (F2) `pypdfium2`. Ruled out: viable, but `pymupdf` is already industry-standard for LN OCR pipelines and has richer page-image control. No protocol abstraction is required by locked input #3, so committing to a single library is fine.
- (F3 — chosen) `pymupdf` (PyMuPDF), added as a hard dep, render via `Pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)` (RGB no-alpha). Matches locked input #3.

**G. Downloader integration**
- (G1) Pyproject dep on `anyflip-downloader`. Ruled out by locked input #2 — no pyproject dep, no vendoring.
- (G2) Reimplement AnyFlip scraping. Ruled out: out of scope, brittle, and reinvents the existing tool.
- (G3 — chosen) Plain `download_anyflip(url, dest, *, executable="anyflip-downloader", timeout_seconds=600) -> None` function that subprocesses the upstream CLI. Plus a post-subprocess assertion that `dest_pdf` exists and is non-empty. Matches locked input #2.

**H. Concurrency primitive**
- (H1) `multiprocessing.Pool` / `ProcessPoolExecutor`. Ruled out: `codex exec` is itself a child process; doubling fan-out via process pool pays pickling cost for zero isolation gain. Also, exception propagation across the process boundary is more fragile.
- (H2) `asyncio.gather` + `asyncio.to_thread`. Ruled out: adds an event-loop layer for a workload that is pure blocking I/O around subprocess calls.
- (H3 — chosen) `concurrent.futures.ThreadPoolExecutor(max_workers=config.workers)`. Matches locked input #13 ("workers=4") with the simplest primitive and clean exception propagation; the subprocess child is the real OS isolation. Per-page tasks call `save_ocr` *inside* the task before returning so partial progress survives a sibling failure.

---

## ADR — Prepare stage, LNVO v2

- **Decision**: Implement Prepare as `run_prepare(...)` + module-mode CLI inside `automations/ln_voice_over_v2/stages/prepare/`. Stage-local seams are **plain module-level functions**: `run_codex_ocr(page_image, *, model, executable, timeout_seconds, prompt) -> OcrPageResult` and `download_anyflip(url, dest, *, executable, timeout_seconds) -> None`. `run_prepare` accepts `ocr_fn: Callable[[Path], OcrPageResult] | None = None` and `download_fn: Callable[[str, Path], None] | None = None` keywords for test injection; when `None` the runner builds a `functools.partial` from `PrepareConfig`. **No `OcrProvider` / `Downloader` Protocol is introduced.** Concurrency is `concurrent.futures.ThreadPoolExecutor(max_workers=config.workers)`. Per-page successes are written to `source/ocr/{page:03d}.json` inside the worker before returning. Add `pymupdf` to `[project.dependencies]`. Widen `automations/ln_voice_over_v2/AGENTS.md` to permit a runner + module-mode CLI **only inside `stages/prepare/`**, while leaving the contract-only rule and the "no empty ports" rule in force for every other stage and for `common/`/`pipeline/`/`series/`.
- **Drivers**: reproducibility on one AnyFlip URL today; OCR billed via ChatGPT sub; downstream contract stability; AGENTS.md "Code Rules" stay intact.
- **Alternatives considered**: see RALPLAN-DR options A–H. Specifically option C1 (Protocol + dataclass) was the round-0 choice and was reversed in round 1 in response to the architect/critic finding that the package's own rule forbids introducing a port before its second implementation exists.
- **Why chosen**: smallest delta to the contract skeleton that produces a real `PreparedVolume`; OCR cost path matches user's existing subscription; per-page resume keeps re-runs cheap; `Callable` seams give equal testability with zero Protocol surface area; the day a second OCR backend appears, promoting `Callable` to Protocol is a one-line refactor.
- **Malformed-cache decision (`recompute` vs `fail-fast`)**: chosen `Literal["recompute","fail-fast"] = "recompute"`. Justification: locked input #11 mandates "per-page resume by default" — a corrupted cache file is operationally indistinguishable from "the prior run crashed half-way through writing this page." Failing fast would force the user to manually delete the file every time; that contradicts the "resume just works" UX driver. Hidden-corruption hazard is mitigated by a `WARNING` log line per recomputed-because-malformed file so the user can spot a pattern (e.g. an OCR-schema regression).
- **`--force` + `--force-ocr` precedence**: when both flags are passed, **`--force` implies `--force-ocr`**. Implementation: argparse's mutually-exclusive group rejects the combination at the CLI layer (usage error, non-zero exit, runner not invoked). Inside the runner, `force=True` short-circuits any `force_ocr` evaluation. Rationale: `--force` already wipes `source/ocr/` and `prepared/`, so honoring `--force-ocr` separately is redundant; allowing the combination would let a user write a script that depends on a partial-force behavior that the runner does not promise.
- **Consequences**:
  - `automations/ln_voice_over_v2/AGENTS.md` becomes stage-scoped: contract-only for non-Prepare stages, runner+CLI allowed in Prepare. The "Code Rules" bullet on empty ports is **unchanged** and remains in force everywhere, including Prepare.
  - The repo now depends on two external CLIs at runtime (`anyflip-downloader`, `codex`). README documents both.
  - `pymupdf` becomes a first-class dep, increasing wheel size for unrelated users of the repo.
- **Follow-ups**:
  - Step 2 plan (Transform) consumes `prepared/volume.json` unchanged; the anchor convention (every `ArtifactPath` is POSIX-relative to `volume_root`) is pinned in this plan's `§validation.py` and README sections.
  - Once a second OCR backend exists, promote `run_codex_ocr` and the analog backend to a Protocol — that's the slice where AGENTS.md's "until a later slice has real ... behavior to represent" clause activates.
  - If multi-volume AnyFlip URLs appear, decide whether `--volume` selects one or the runner emits multiple prepared volumes (see Open Questions).

---

## AGENTS.md scope change

**Current paragraph (`automations/ln_voice_over_v2/AGENTS.md`, "Boundaries" section, bullet 3, lines 25-26):**

> - Do not add CLI commands, OCR, parsing algorithms, LLM prompts, TTS rendering,
>   visual rendering, data-porting logic, or plugin frameworks here.

This rule is too strict for the Prepare slice, which legitimately owns OCR, an LLM prompt, and a module-mode CLI. Other stages remain contract-only until their own implementation slice lands.

**Current paragraph (`automations/ln_voice_over_v2/AGENTS.md`, "Code Rules" section, bullet 4, lines 35-36) — UNCHANGED, quoted here for the record:**

> - Do not add empty runners, ports, adapters, or services until a later slice
>   has real orchestration or external-boundary behavior to represent.

This rule **stays in force everywhere, including `stages/prepare/`**. The new code in this slice does not introduce a Protocol/port/adapter; OCR and download seams are plain module-level functions injected via `Callable` keywords. The `Code Rules` bullet is therefore not amended.

**Proposed replacement for the "Boundaries" bullet (replace the single bullet quoted above with the following two bullets):**

> - Stages other than `stages/prepare/` remain contract-only. Do not add CLI
>   commands, OCR, parsing algorithms, LLM prompts, TTS rendering, visual
>   rendering, data-porting logic, or plugin frameworks in `stages/transform/`,
>   `stages/dialogue/`, `stages/scenes/`, `stages/generation/`, or anywhere
>   under `common/`, `pipeline/`, or `series/`.
> - `stages/prepare/` may add a runner, a `python -m`-style CLI, PDF
>   rasterization, one OCR prompt string, and plain module-level seam
>   functions (`run_codex_ocr`, `download_anyflip`) that subprocess external
>   CLIs. These seams are kept as free functions injected via `Callable`
>   keywords, **not** as Protocols/ports/adapters, so the "Code Rules" bullet
>   on empty ports remains satisfied. New external runtime dependencies must
>   be installable via PyPI (e.g. `pymupdf`) or documented in the package
>   README (e.g. `anyflip-downloader`, `codex`). No vendoring.

The "Code Rules" section's prohibition on "empty runners, ports, adapters, or services" stays — there are none in this slice.

---

## File-level change list

### Artifact-path anchor convention (applies to every embedded path)

**Every `ArtifactPath` in `prepared/volume.json` is POSIX-relative to `volume_root(data_root, series, volume)` — i.e. the directory that contains both `source/` and `prepared/`.** The artifact lives at `volume_root / "prepared" / "volume.json"` but its embedded paths step **up two levels** to the volume root, not one level to `prepared/`. The runner constructs absolute filesystem paths only via `paths.volume_root(...) / artifact_path`; nothing else in this stage joins paths against any other anchor. `validate_prepared_volume` enforces this rule with `(volume_root / path).is_file()` checks for every `text_unit.source_path`, every `media.path`, and every `media.source_path`. The README repeats this rule as a single-line legend under the runtime layout block so downstream stages do not guess.

### Page-index dual convention (applies to every page-keyed value)

- Filesystem page PNGs are **1-indexed**: `source/pages/001.png`, …, `source/pages/{N:03d}.png`.
- `PreparedTextUnit.source_locator = {"page": <int>}` is **1-indexed** (matches the filesystem).
- `PreparedTextUnit.order` and the integer suffix of `text_unit_id` (`unit_{page-1:06d}`) are **0-indexed** (matches the contract's `Field(ge=0)`).
- `PreparedMedia.order` is **0-indexed** (`seq - 1`); the `seq` numeric suffix in `media_id` (`illustration-{seq:03d}`) and the on-disk filename is **1-indexed**.

This dual convention is restated in `§text_units.py` intent and in the README so Transform's planner does not have to derive it.

### New files under `automations/ln_voice_over_v2/stages/prepare/`

#### `__init__.py` (update)
- Re-export `run_prepare`, `PrepareConfig`, `PrepareResult`, `OcrPageResult`, `run_codex_ocr`, `download_anyflip` for importers.
- Keep contract re-exports (`PreparedVolume`, `PreparedTextUnit`, `PreparedMedia`) from `contracts.py`.

#### `__main__.py`
- Thin argparse wrapper. Parses `--url`, `--series`, `--volume`, `--story-profile` (optional), `--data-root` (optional, defaults to `DEFAULT_PROJECT_DATA_ROOT`), `--workers` (int, default 4), `--ocr-model` (str, default `gpt-5-mini`), `--force`, `--force-ocr`. Calls `run_prepare(...)`. Prints the prepared volume path on success; prints a structured error on failure and exits non-zero.
- **Mutual exclusion**: `--force` and `--force-ocr` are configured via `argparse.add_mutually_exclusive_group()` so passing both yields a usage error before the runner is invoked. The implicit-resume default is taken when neither is set.
- **`ProfileId` parsing**: `--story-profile` is accepted as a plain `str` by argparse; the Pydantic constructor inside `PrepareConfig` (via the `ProfileId` `StringConstraints` regex from `common/ids.py`) enforces the slug regex. Do **not** import the regex into argparse.
- **Logging setup**: configures `logging.getLogger("ln_voice_over_v2.prepare")` with a stderr handler at `INFO` level. The malformed-cache `WARNING` lines and per-page progress messages from `runner.py` land here.
- Public surface:
  - `def main(argv: list[str] | None = None) -> int`
  - `if __name__ == "__main__": raise SystemExit(main())`

#### `runner.py`
- Orchestrator. Owns the per-page pipeline: download PDF → rasterize → resume-or-OCR (concurrent) → assemble `PreparedVolume` → validate → atomic write.
- **Module-level constant**: `SOURCE_PROFILE: Final[str] = "pdf-llm-ocr"` — set unconditionally on every emitted `PreparedVolume.source_profile` regardless of CLI flags.
- Public surface:
  - ```python
    @dataclass(frozen=True)
    class PrepareConfig:
        anyflip_url: str
        series: SeriesId
        volume: VolumeId
        data_root: Path = DEFAULT_PROJECT_DATA_ROOT
        story_profile: ProfileId | None = None  # defaults to `series`
        ocr_model: str = "gpt-5-mini"
        workers: int = 4
        force: bool = False
        force_ocr: bool = False
    ```
  - ```python
    @dataclass(frozen=True)
    class PrepareResult:
        prepared_volume_path: Path
        prepared_volume: PreparedVolume
        page_count: int       # equals len(prepared_volume.text_units); see "Pinned invariants" below
        illustration_count: int
    ```
  - ```python
    def run_prepare(
        config: PrepareConfig,
        *,
        download_fn: Callable[[str, Path], None] | None = None,
        ocr_fn: Callable[[Path], OcrPageResult] | None = None,
    ) -> PrepareResult: ...
    ```
  - Internal helpers (module-private): `_ensure_layout`, `_resolve_seams`, `_ocr_all_pages`, `_build_text_units`, `_build_media`, `_validate_or_raise`.
- **Pinned invariants**:
  - `prepared.source_profile = SOURCE_PROFILE` (i.e. `"pdf-llm-ocr"`) is set unconditionally.
  - `prepared.story_profile = config.story_profile or config.series` (i.e. defaults to the series id when omitted).
  - `prepared.text_units` and `prepared.media` are ordered by `order` ascending before construction.
  - `PrepareResult.page_count == len(prepared_volume.text_units)`. Source of truth: the rasterizer result (`len(rasterized)`). Equality holds by construction because the runner emits exactly one text unit per rasterized page; a page that fails to rasterize aborts the run before text-unit assembly.
  - Every `ArtifactPath` in the constructed `PreparedVolume` is POSIX-relative to `paths.volume_root(config.data_root, config.series, config.volume)`. The runner never embeds absolute paths.
- **Seam wiring**: when `download_fn`/`ocr_fn` are `None`, the runner builds them as
  `download_fn = functools.partial(download_anyflip, executable="anyflip-downloader", timeout_seconds=600)` and
  `ocr_fn = functools.partial(run_codex_ocr, model=config.ocr_model, executable="codex", timeout_seconds=180, prompt=OCR_PROMPT)`.
  This is the seam tests inject through.
- **Ordering guarantee passed to `text_units.py` / `media.py`**: the runner sorts both `rasterized` (returned by `rasterize_pdf`) and `ocr_results` by 1-indexed page number ascending before zipping. `build_text_units` and `collect_media` may assume strict same-length, same-order alignment.
- **Concurrency primitive**: `concurrent.futures.ThreadPoolExecutor(max_workers=config.workers)`. Each per-page worker:
  1. Resolves the cache path `source/ocr/{page:03d}.json`.
  2. Under default resume, if the cache file exists, attempt `OcrPageResult.model_validate_json(...)`. On success, return the cached result. On failure (file exists but does not parse to the strict shape), emit one `logger.warning("source/ocr/%03d.json failed strict parse; recomputing", page)` line and fall through to recompute. Under `--force-ocr` or `--force`, skip the cache entirely.
  3. Call `ocr_fn(page_image)` to compute fresh.
  4. **Before returning**, write the result via `save_ocr(cache_path, result)` so partial progress is durable. A sibling worker raising does NOT roll back the file this worker has already written.
  5. Return the `OcrPageResult` plus the 1-indexed page number so the runner can assemble in deterministic order.
- **Partial-progress guarantee**: if page 2 raises, page 1's `source/ocr/001.json` is on disk before any join site sees the exception. A follow-up no-flag run resumes page 1 from cache and only re-OCRs page 2.
- **No retry policy**: a worker's exception (subprocess non-zero exit, malformed JSON, timeout) propagates through `Future.result()` and aborts the entire run. Already-committed pages remain on disk.
- **Logging**: `logger = logging.getLogger("ln_voice_over_v2.prepare")`. The malformed-cache recompute is the one `WARNING`-level line in normal operation; success and per-page completion are logged at `INFO`.

#### `downloader.py`
- One free function. No class. No Protocol.
- Public surface:
  - ```python
    def download_anyflip(
        url: str,
        dest_pdf: Path,
        *,
        executable: str = "anyflip-downloader",
        timeout_seconds: int = 600,
    ) -> None:
        """Download an AnyFlip flipbook to a single PDF at `dest_pdf`.

        Idempotent: if `dest_pdf` already exists and is non-empty,
        returns immediately without invoking the CLI.
        After a successful (zero-exit) subprocess call, asserts that
        `dest_pdf` exists and `dest_pdf.stat().st_size > 0`; otherwise
        raises `RuntimeError` with the captured stderr.
        """
    ```
  - Intent: shell out to `executable` with `--url <url> --output <dest_pdf>` (final flag names verified against the tool's `--help` at implementation time; this plan locks the seam shape and the failure-mode contract, not the upstream tool's flag spelling). Use `subprocess.run(..., capture_output=True, text=True, timeout=timeout_seconds)`. Non-zero exit → `RuntimeError(stderr)`. Zero exit but `dest_pdf` missing or zero-byte → `RuntimeError("anyflip-downloader exited 0 but produced no PDF: " + stderr)`. Do not capture stdout into the contract.

#### `rasterizer.py`
- Pure PyMuPDF wrapper. No protocol.
- Public surface:
  - ```python
    @dataclass(frozen=True)
    class RasterizedPage:
        page: int       # 1-indexed
        path: Path
    ```
  - ```python
    def rasterize_pdf(
        pdf_path: Path,
        pages_dir: Path,
        *,
        dpi: int = 200,
        force: bool = False,
    ) -> list[RasterizedPage]:
        """Render every page of `pdf_path` to `pages_dir/{page:03d}.png`."""
    ```
  - Intent: `import pymupdf as fitz`. Open with `fitz.open(pdf_path)`. For each page index `i` (0-indexed in PyMuPDF; the on-disk filename uses `page = i + 1`), render via `page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)` (RGB, no alpha) and write `{pages_dir}/{i+1:03d}.png`. Skip rendering if the target file exists and `force` is False. After the loop, **reject empty PDFs**: if `len(rasterized) < 1`, raise `RuntimeError(f"PDF at {pdf_path} has zero pages")` before any OCR budget is spent. Returns one `RasterizedPage` per page in ascending 1-indexed order.

#### `prompts.py`
- One module-level constant. The prompt is the *contract* the OCR side honors.
- Public surface:
  - ```python
    OCR_PROMPT: str
    ```
  - Intent: instruct the model to OCR the page and emit **only** a single JSON object `{"transcript": str, "is_illustration": bool}` with:
    - no prose, no preamble, no postamble;
    - **no markdown code fences** (`` ```json ... ``` `` or `` ``` ... ``` ``); raw JSON only;
    - no trailing newline noise;
    - for two-column pages: read both columns top-to-bottom, then left-to-right; preserve paragraph breaks;
    - do not translate; preserve furigana inline when present;
    - if the page is a full-bleed illustration with no readable text, set `transcript=""` and `is_illustration=true`.
  - The "no markdown code fences" instruction is the single most important line in the prompt because that is `gpt-5-mini`'s most common structured-output failure mode.

#### `ocr.py`
- Plain `OcrPageResult` Pydantic model, plain `run_codex_ocr` function, plain cache helpers. **No Protocol, no ABC, no port.**
- Public surface:
  - ```python
    class OcrPageResult(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        transcript: str
        is_illustration: bool
    ```
  - ```python
    def run_codex_ocr(
        page_image: Path,
        *,
        model: str = "gpt-5-mini",
        executable: str = "codex",
        timeout_seconds: int = 180,
        prompt: str = OCR_PROMPT,
    ) -> OcrPageResult:
        """Subprocess `codex exec` and parse strict JSON."""
    ```
  - Intent: build argv as
    `[executable, "exec", "-i", str(page_image), "-m", model, "--ephemeral", "--skip-git-repo-check", "-s", "read-only", prompt]`.
    Call `subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_seconds, check=True)`. On non-zero exit, `check=True` raises `CalledProcessError`; wrap into `RuntimeError` with stderr in the message. On zero exit, parse `OcrPageResult.model_validate_json(completed.stdout.strip())`. On parse failure, raise `ContractValidationError([ValidationProblem(code="ocr_malformed", message=f"{parse_err} | stderr={completed.stderr[:500]}", path=str(page_image))])`. Stderr is **only** consulted for error messages; it is never parsed into the contract. No retries.
  - ```python
    def load_cached_ocr(path: Path) -> OcrPageResult | None:
        """Return the parsed cache or None (missing or malformed)."""
    ```
  - ```python
    def save_ocr(path: Path, result: OcrPageResult) -> None:
        """Atomic write via tempfile.NamedTemporaryFile + tmp_path.replace(path)."""
    ```
  - **`save_ocr` and `load_cached_ocr` replicate the atomic-write primitive locally** (`tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8")` + `tmp_path.replace(path)`). They do **not** call `common/json_io.save_json_contract` because `OcrPageResult` is not a `PersistedArtifact` and lacks `schema_version` / `artifact_kind`. The runner distinguishes "missing" from "malformed" by checking `path.exists()` before calling `load_cached_ocr`; if the file exists but `load_cached_ocr` returns `None`, the runner emits the `WARNING` log line described in `§runner.py`.

#### `media.py`
- Build the `PreparedMedia` list from per-page OCR results + page images.
- Public surface:
  - ```python
    def collect_media(
        ocr_results: list[OcrPageResult],
        rasterized: list[RasterizedPage],
        volume_root: Path,
        *,
        rebuild: bool = False,
    ) -> tuple[PreparedMedia, ...]:
        """Copy illustration pages into `prepared/media/` and return contract rows.

        When `rebuild=True`, delete every existing file under `prepared/media/`
        before copying the new set so stale illustration PNGs (for pages no
        longer flagged as is_illustration) do not survive a recompute.
        """
    ```
  - Intent: zip `rasterized` with `ocr_results` (asserted same length, same 1-indexed page order — guaranteed by the runner before calling). For every page with `is_illustration == true`, allocate a sequential `seq` starting at 1, copy `source/pages/{page:03d}.png` → `prepared/media/illustration-{seq:03d}.png`, and emit a `PreparedMedia` with `media_id="illustration-{seq:03d}"`, `media_type=MediaType.ILLUSTRATION`, `path="prepared/media/illustration-{seq:03d}.png"`, `source_path="source/pages/{page:03d}.png"`, `order=seq-1`. The runner passes `rebuild=True` under `--force` or `--force-ocr` and `rebuild=False` under the default resume path.

#### `text_units.py`
- Build the `PreparedTextUnit` list.
- Public surface:
  - ```python
    def build_text_units(
        ocr_results: list[OcrPageResult],
        rasterized: list[RasterizedPage],
    ) -> tuple[PreparedTextUnit, ...]:
        """Emit one `PreparedTextUnit` per page in 1-indexed page order.

        Page-index convention: filesystem page numbers and the `page` key in
        `source_locator` are 1-indexed; `order` and the integer suffix of
        `text_unit_id` are 0-indexed. Illustration-only pages still emit a
        unit with empty `text` so `order` stays contiguous.
        """
    ```
  - Intent: for each (page, OcrPageResult) pair (page is the 1-indexed filesystem page number), emit `PreparedTextUnit(text_unit_id=f"unit_{page-1:06d}", order=page-1, text=ocr.transcript, source_path=f"source/pages/{page:03d}.png", source_locator={"page": page})`. `source_locator["page"]` is an `int` (allowed by `PreparedTextUnit.source_locator: dict[str, str | int | float | bool | None]`).

#### `validation.py`
- Cross-artifact validation gate before write. **Anchor rule pinned in writing here.**
- Public surface:
  - ```python
    def validate_prepared_volume(
        volume: PreparedVolume,
        volume_root: Path,
    ) -> None:
        """Raise `ContractValidationError` if filesystem invariants fail.

        Anchor convention: every ArtifactPath in `volume` (text_unit.source_path,
        media.path, media.source_path) is POSIX-relative to `volume_root` — the
        directory that contains both `source/` and `prepared/`. Absolute
        filesystem locations are computed as `volume_root / artifact_path`.
        """
    ```
  - Intent: checks (each emits one `ValidationProblem` on failure):
    - `text_units` non-empty (`code="text_units_empty"`).
    - `order` values unique and contiguous from 0 across `text_units` (`code="text_unit_order_gap"` / `"text_unit_order_duplicate"`).
    - For each `text_unit.source_path`, assert `(volume_root / text_unit.source_path).is_file()` (`code="text_unit_source_missing"`).
    - For each `media.path`, assert `(volume_root / media.path).is_file()` (`code="media_path_missing"`).
    - For each `media.source_path`, assert `(volume_root / media.source_path).is_file()` (`code="media_source_missing"`).
    - `media.order` values unique and contiguous from 0 (`code="media_order_gap"` / `"media_order_duplicate"`).
    - Pydantic-level validation (extra=forbid, types, `Field(ge=0)`, regex on ids) is already enforced by `PreparedVolume`'s construction; this function only adds filesystem-cross-checks.

### Existing files that must change

- `automations/ln_voice_over_v2/AGENTS.md` — replace the one "Boundaries" bullet as described in the AGENTS.md scope-change section above. The "Code Rules" bullet on empty ports is **not** touched.
- `automations/ln_voice_over_v2/README.md` — add prerequisites, CLI example, layout, re-run flags, test invocation (see README updates section).
- `automations/ln_voice_over_v2/stages/prepare/__init__.py` — re-export the new public surface listed above.
- `pyproject.toml` — add `pymupdf` to `[project.dependencies]` (see pyproject section).

No file in `common/`, `pipeline/`, `series/`, or `stages/*/contracts.py` is touched.

---

## New pyproject.toml dep

The current `[project.dependencies]` is a single flat list and there is no v2 extra. Add `pymupdf` to the flat list. Exact diff hunk:

```diff
 dependencies = [
     "mss>=9.0",
     "Pillow>=10.0",
     "typer>=0.9.0",
     "pyautogui>=0.9.54",
     "pydantic>=2.12.5",
+    "pymupdf>=1.24",
 ]
```

`anyflip-downloader` and `codex` remain runtime CLI prereqs documented in the package README — not added to `pyproject.toml` per locked input #2.

---

## README updates

Append the following sections to `automations/ln_voice_over_v2/README.md` (after the existing skeleton description):

### Prepare stage (Step 1)

**Runtime prerequisites (not installed by `pyproject.toml`):**

- `anyflip-downloader` on `PATH` (install per the upstream project's instructions; the LNVO v2 runner only shells out to it).
- `codex` CLI on `PATH`, and the user must have signed in once via `codex login` using their ChatGPT subscription. The runner does not handle auth.
- The default OCR model id is `gpt-5-mini`. If the user's installed `codex` CLI rejects that id, every page will fail uniformly during the first run — change the `--ocr-model` flag to a model the CLI accepts.

**CLI usage:**

```bash
python -m automations.ln_voice_over_v2.stages.prepare \
    --url "https://anyflip.com/<flipbook-url>" \
    --series classroom-of-the-elite-year-2 \
    --volume v4
```

Optional flags: `--story-profile <slug>` (defaults to `<series>`), `--data-root <path>` (defaults to `~/.assistant/ln_voice_over_v2/projects`), `--workers <int>` (default 4), `--ocr-model <name>` (default `gpt-5-mini`), `--force`, `--force-ocr`.

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

**Run the prepare-stage tests:**

```bash
pytest tests/automations/ln_voice_over_v2/stages/prepare/
```

---

## Test plan

Tests live under `tests/automations/ln_voice_over_v2/stages/prepare/`. The real `codex` CLI and the real `anyflip-downloader` CLI are NEVER invoked. Both seams are injected as test callables (`download_fn=`, `ocr_fn=`).

A small fixture PDF (1–2 pages) is committed under `tests/automations/ln_voice_over_v2/stages/prepare/fixtures/sample.pdf` and is generated once via `pymupdf` in `conftest.py` if not present (or shipped as a tiny binary — implementer's choice; either way tests must not depend on network).

Pytest invocation: `pytest tests/automations/ln_voice_over_v2/stages/prepare/`.

### `test_downloader.py`
- `download_anyflip` invokes the configured executable with the right argv shape (assert via `unittest.mock.patch` on `subprocess.run`).
- If the binary exits non-zero, `download_anyflip` raises `RuntimeError` and the `dest_pdf` is not created.
- If the binary exits zero but `dest_pdf` does not exist (or is zero-byte), `download_anyflip` raises `RuntimeError` with stderr in the message.
- Idempotency: if `dest_pdf` already exists and is non-empty, the subprocess is NOT invoked.

### `test_rasterizer.py`
- `rasterize_pdf` on the 1–2 page fixture produces exactly `{001.png, ...}` files in the target dir, 1-indexed.
- Re-running without `force=True` does not rewrite existing PNGs (assert mtime unchanged).
- Re-running with `force=True` rewrites them (assert mtime changes).
- Returned `RasterizedPage` list is sorted by `page` ascending.
- Empty PDF (zero pages) → `RuntimeError`.
- Renders RGB without alpha (`PIL.Image.open(path).mode == "RGB"` after the call).

### `test_ocr_function.py`
- `run_codex_ocr` builds the exact argv `[executable, "exec", "-i", str(image), "-m", model, "--ephemeral", "--skip-git-repo-check", "-s", "read-only", prompt]`.
- Valid JSON stdout → `OcrPageResult(transcript=..., is_illustration=...)`.
- Stdout with markdown fences (`` ```json ... ``` ``) → `ContractValidationError` with code `ocr_malformed`; the error message includes a slice of stderr for debuggability.
- Stdout with trailing prose (`{"transcript":"x","is_illustration":false}\nOK done`) → `ContractValidationError` with code `ocr_malformed`.
- `OcrPageResult` rejects extra keys (`extra="forbid"`).
- `subprocess.run` is called with `stdout=PIPE, stderr=PIPE, text=True`; assert via mock.
- Non-zero exit → `RuntimeError` whose message contains stderr.
- `load_cached_ocr` returns `None` for missing files and for files that fail to parse (extra key, missing key, non-JSON); returns the model for valid files.
- `save_ocr` writes atomically: the destination either contains the full new content or the prior content; never a half-written file (assert by patching `tmp_path.replace` to raise mid-call and checking the destination is unchanged).

### `test_text_units.py`
- Given N page rasters + N OcrPageResults, `build_text_units` emits N units with contiguous `order` from 0 and ids `unit_000000`, `unit_000001`, ….
- `source_locator["page"]` equals the 1-indexed filesystem page number.
- Illustration-only pages still emit a unit (with empty `text`) so `order` stays contiguous.
- The integer suffix of `text_unit_id` (zero-padded 6 digits) equals `order`, i.e. zero-indexed.

### `test_media.py`
- Only pages flagged `is_illustration=True` produce media entries.
- `seq` numbering is 1-based and contiguous across illustrations only.
- The illustration PNGs are copied to `prepared/media/illustration-{seq:03d}.png` and match the source page bytes.
- `order = seq - 1`.
- `rebuild=True` deletes any pre-existing files under `prepared/media/` before copying the new set; a pre-existing `illustration-013.png` for a page no longer flagged is gone after the call.
- `rebuild=False` leaves `prepared/media/` alone for pages whose `is_illustration` verdict is unchanged.

### `test_validation.py`
- Missing `text_unit.source_path` file (resolved against `volume_root`) → `ContractValidationError` with code `text_unit_source_missing`.
- Empty `text_units` → `ContractValidationError` with code `text_units_empty`.
- Non-contiguous `text_unit.order` (e.g. 0,1,3) → `ContractValidationError` with code `text_unit_order_gap`.
- Duplicate `text_unit.order` → `ContractValidationError` with code `text_unit_order_duplicate`.
- Missing `media.path` or `media.source_path` file (resolved against `volume_root`) → `ContractValidationError` with the matching code.

### `test_runner_resume.py`
- Pre-existing valid `source/ocr/{page:03d}.json` is reused: the injected `ocr_fn` is asserted NOT called for that page.
- Pre-existing **invalid** `source/ocr/{page:03d}.json` (e.g. `{"transcript": "x"}` missing `is_illustration`; or `{"transcript": "x", "is_illustration": false, "extra": 1}` with extra key) causes the runner to emit exactly one `logging.WARNING` line matching `failed strict parse; recomputing` for that page (captured via `caplog`) and the injected `ocr_fn` IS called for that page.
- `--force` causes recomputation of OCR AND re-rasterization (assert both fakes called every page) and rebuilds `prepared/media/`.
- `--force-ocr` causes OCR recomputation only; pre-existing page rasters are reused; `prepared/media/` is rebuilt.
- **Mutual exclusion**: invoking `main(["--url", "...", "--series", "s", "--volume", "v", "--force", "--force-ocr"])` returns a non-zero exit and does not call the runner (argparse usage error).
- **Partial-progress test**: configure a `fake_ocr_fn` that returns success for page 1 and raises for page 2. Run with `workers=2`. After the exception propagates and the run aborts, assert that `source/ocr/001.json` exists on disk and parses to a valid `OcrPageResult`; assert that `source/ocr/002.json` does NOT exist. Then re-run with no flags and a fake that succeeds for page 2; assert that page 1's `ocr_fn` is NOT called the second time (cache hit) and that the run completes successfully.
- **Rasterize-without-OCR resume**: configure a state where `source/pages/*.png` exists for every page but `source/ocr/` is empty. Run with no flags. Assert that `rasterize_pdf` is invoked but performs no writes (mtimes unchanged on the page PNGs), that `ocr_fn` is called once per page, and that the resulting `PreparedVolume` is complete.

### `test_runner_end_to_end.py`
- Inject a `fake_download_fn` that copies the fixture PDF to `source/volume.pdf` and a `fake_ocr_fn` returning canned results (e.g. page 1: prose, page 2: illustration).
- Assert `run_prepare` returns a `PrepareResult` whose `prepared_volume_path` exists and round-trips: `PreparedVolume.model_validate_json(path.read_text())` produces an equal model.
- Assert `prepared.source_profile == "pdf-llm-ocr"`.
- Assert `prepared.story_profile == prepared.series` when `story_profile` arg is omitted; assert it equals the explicit value when provided.
- Assert `len(prepared.text_units) == fixture_page_count` and `result.page_count == len(prepared.text_units)`.
- Assert media count equals the number of illustration pages in the fixture.
- **Anchor-convention end-to-end assertion**: for every `unit` in `prepared.text_units`, assert `(volume_root / unit.source_path).is_file()`. For every `media` in `prepared.media`, assert `(volume_root / media.path).is_file()` and `(volume_root / media.source_path).is_file()`. This pins the anchor convention in code, not just in prose.

---

## Manual smoke test (single AnyFlip URL)

The user will run the following by hand against one real AnyFlip URL:

```bash
python -m automations.ln_voice_over_v2.stages.prepare \
    --url "https://anyflip.com/<flipbook-url>" \
    --series classroom-of-the-elite-year-2 \
    --volume v4
```

After a successful run, the following on-disk artifacts must exist:

```
~/.assistant/ln_voice_over_v2/projects/classroom-of-the-elite-year-2/v4/
  source/
    volume.pdf
    pages/001.png ... {N:03d}.png
    ocr/001.json ... {N:03d}.json        # each parses to {"transcript": str, "is_illustration": bool}
  prepared/
    volume.json
    media/illustration-001.png ... illustration-{M:03d}.png   # M = # of illustration pages
```

**Success invariant (one line):**

```python
prepared = PreparedVolume.model_validate_json((volume_root / "prepared" / "volume.json").read_text())
assert prepared.source_profile == "pdf-llm-ocr" and len(prepared.text_units) >= EXPECTED_PAGE_COUNT_FOR_THE_VOLUME
```

where `EXPECTED_PAGE_COUNT_FOR_THE_VOLUME` is whatever page count the AnyFlip flipbook actually has (the user knows it for their target volume).

**Sanity sub-check (OCR quality at 200 DPI):** open the first 5 entries of `source/ocr/*.json` and spot-check the `transcript` field. If kana are garbled or columns are interleaved out of order, re-run the slice with a higher DPI. (At this slice the rasterizer DPI is locked at 200 inside `rasterize_pdf`; exposing it as a CLI flag is deferred to Step 2 or a follow-up.)

---

## Out of scope (explicit)

The following are **not** part of this slice and must not be touched:

- Transform, Dialogue, Scenes, Generation stages — contracts and code.
- Legacy `automations/ln_voice_over/` migration (no data, no code is ported).
- Non-AnyFlip sources (Bookwalker, EPUB, plain text, image dumps).
- Non-PDF prepared inputs.
- Any manual-review UI, web UI, or human-in-the-loop OCR correction.
- Caching, retry policy, exponential backoff for `codex exec` failures.
- Multi-volume AnyFlip URLs (one URL ↔ one `(series, volume)` for this slice).
- Translation, romanization, or text post-processing of OCR output.
- A second OCR backend (will trigger the `Callable` → `Protocol` promotion in a future slice, per ADR follow-ups).

---

## Open questions

These are residual ambiguities the implementer should resolve at coding time or briefly check with the user. They do not block the plan.

1. **PyMuPDF DPI default.** This plan locks 200 DPI in `rasterize_pdf` because that's a widely-used default for OCR of light-novel pages, but the user has not pinned a number. If `gpt-5-mini` underperforms on small kana the implementer should bump to 300 DPI before re-OCR. (Bumping the default raises file size ~2.25× and OCR latency.)
2. **Multi-volume AnyFlip URLs.** Some AnyFlip "books" are actually composite uploads with chapter dividers. Locked input treats one URL as one volume. If a real URL turns out to span multiple volumes, the runner should fail loudly rather than silently flatten — but choosing the failure surface is deferred until we see such a URL.
3. **Two-column OCR ordering.** The OCR prompt instructs "both columns top-to-bottom, then left-to-right." If `gpt-5-mini` doesn't reliably honor this on a real LN page, we may need to add a page-side hint or render at higher DPI. No automated check is feasible at this slice; visual spot-check is the user's responsibility during the manual smoke test.
4. **`anyflip-downloader` flag spelling.** The seam shape is locked but the precise flag names (`--url`, `--output` vs. positional vs. `-u`/`-o`) must be verified against the upstream tool's `--help` during implementation. This does not change any contract.
5. **Empty-transcript illustration units.** Pages flagged `is_illustration=true` with empty `transcript` still emit a `PreparedTextUnit` with empty `text` (to keep `order` contiguous). Transform may later choose to filter these. Confirm during Step 2 planning, not now.
6. **`codex exec` flag stability.** The locked argv (`-i`, `-m`, `--ephemeral`, `--skip-git-repo-check`, `-s read-only`) assumes one `codex` CLI version. If the user's installed version drops or renames any of these flags, the runner currently surfaces a generic non-zero-exit `RuntimeError` with stderr in the message. The implementer should verify the argv survives `codex exec --help` on the user's machine before the manual smoke run; if not, this becomes a one-line plan amendment, not a contract change.
7. **`gpt-5-mini` as the OCR model id.** Locked input #4 names this; if the codex-CLI lookup rejects the id, every page will fail uniformly during the smoke test. The runner does not validate the model id ahead of time — `codex exec` is the authority. The README flags this so the user catches it fast.
8. **`source_locator` shape.** This slice emits only `{"page": <int>}`. Transform may want richer locators (`column_hint`, `dpi`, `pdf_bookmark`) later — out of scope here, but flagged so Step 2's planner remembers that today's locator is intentionally minimal.

---

## Revisions applied (round 1)

| # | Architect + Critic merged revision | Plan section header |
|---|---|---|
| 1 | Drop `OcrProvider` / `Downloader` Protocols; use `Callable` injection seams (architect #1, critic C1) | `ADR — Prepare stage, LNVO v2`; `AGENTS.md scope change`; `runner.py`; `downloader.py`; `ocr.py` |
| 2 | Pin artifact-path anchor convention (architect #2, critic M1) | `Artifact-path anchor convention (applies to every embedded path)`; `validation.py`; `README updates`; `runner.py` |
| 3 | Partial-progress + malformed-cache guarantees in runner (architect #3, critic M4 + M5) | `runner.py`; `ocr.py` |
| 4 | `--force-ocr` media-cleanup semantics (architect #4, critic M3) | `media.py`; `README updates` |
| 5 | Dual page-index convention documented (architect #5, critic m4) | `Page-index dual convention (applies to every page-keyed value)`; `text_units.py`; `README updates` |
| 6 | Runtime anchor + resume tests in test plan (architect #6, critic M2 + M4 + M5) | `test_runner_end_to_end.py`; `test_runner_resume.py`; `test_validation.py` |
| 7 | OCR prompt forbids markdown fences; subprocess captures stderr; both visible in error message (architect #7, critic gap) | `prompts.py`; `ocr.py`; `test_ocr_function.py` |
| 8 | Pin concurrency primitive: `ThreadPoolExecutor(max_workers=N)`, per-task `save_ocr` before return (critic M6) | `runner.py` |
| 9 | Mutual exclusion of `--force` / `--force-ocr` enforced at argparse; `--force` implies `--force-ocr` (critic risk-mitigation) | `__main__.py`; `ADR — Prepare stage, LNVO v2`; `README updates`; `test_runner_resume.py` |
| 10 | Downloader asserts `dest_pdf` exists and non-empty after zero-exit (critic risk-mitigation) | `downloader.py`; `test_downloader.py` |
| 11 | `OcrPageResult` is not a `PersistedArtifact`; `save_ocr` replicates atomic-write primitive locally (critic m1) | `ocr.py` |
| 12 | `source_profile = "pdf-llm-ocr"` stated as a runner invariant (critic locked-input audit) | `runner.py` ("Pinned invariants") |
| 13 | Explicit pytest invocation command (critic acceptance-criteria audit) | `README updates`; `Test plan` |
| 14 | Open Question on `codex exec` flag stability + `gpt-5-mini` id lookup (critic m3) | `Open questions` (#6, #7); `README updates` |
| 15 | Pin PNG color mode: `Pixmap(matrix=..., alpha=False)` (critic gap) | `rasterizer.py`; `test_rasterizer.py` |
