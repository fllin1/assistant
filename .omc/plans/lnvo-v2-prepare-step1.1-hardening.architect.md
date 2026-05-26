---
role: architect
target_plan: lnvo-v2-prepare-step1.1-hardening.md
timestamp: 2026-05-26T00:00:00Z
verdict: ITERATE
---

# Architect Review — LNVO v2 Step 1.1 (Prepare Hardening)

This review is a structural critique of the plan at
`.omc/plans/lnvo-v2-prepare-step1.1-hardening.md` (HEAD `c6d387f` on
`feat/lnvo-v2-prepare-step1`). It is read-only. The Critic runs after this
review and should treat the **Steelman antithesis**, the **Tradeoff tensions**,
the **Synthesis**, and the **Principle-violation flags** as the substantive
agenda — not as background.

I read, before forming any conclusion:

- `automations/ln_voice_over_v2/stages/prepare/runner.py` (current orchestration shape and the only call site of `build_text_units`)
- `automations/ln_voice_over_v2/stages/prepare/ocr.py` (`OcrPageResult`, the `prompt: str = OCR_PROMPT` default-arg sentinel, the `run_codex_ocr` exception surface)
- `automations/ln_voice_over_v2/stages/prepare/text_units.py` (the `_assert_page_alignment` and 1-indexed convention)
- `automations/ln_voice_over_v2/stages/prepare/contracts.py` (`PreparedTextUnit`)
- `automations/ln_voice_over_v2/stages/prepare/prompts.py` (current single `OCR_PROMPT`)
- `automations/ln_voice_over_v2/stages/prepare/validation.py` (current invariants — no `needs_review` reference, which is intentional and locked)
- `automations/ln_voice_over_v2/common/artifacts.py` (`ContractModel` config: `frozen=True, extra="forbid"`)
- `automations/ln_voice_over_v2/AGENTS.md` (Boundaries + Code Rules; especially the "no empty ports/adapters" bullet)
- `docs/lnvo/01-prepare.md` (Prepared Text Unit reference page — the doc the plan extends)
- `tests/automations/ln_voice_over_v2/stages/prepare/test_runner_end_to_end.py` and `test_text_units.py` (existing test shape and fixture footprint)

Every numbered finding below cites a file and a line.

---

## 1. Steelman antithesis (the sharpest single counter-proposal)

**Antithesis — "Refusal is a `run_codex_ocr` failure mode, not a `runner.py`
concern; the retry loop and `_looks_like_refusal` belong inside `ocr.py`."**

The plan localizes the retry loop inside `runner.py::_ocr_one_page` and exposes
the seam `ocr_fn: Callable[[Path], OcrPageResult]` unchanged. That preserves
the test seam — which is the plan's main argument — but it also pushes a
boundary concern (model refused a request) one layer above the boundary where
the request actually happens. The strongest alternative is: keep
`runner.py` ignorant of refusal, and let `run_codex_ocr` itself take a
`prompts: Sequence[str]` parameter (or a `max_attempts: int` argument) and
internally cycle through them, raising one specific exception
(`OcrRefusalExhausted`) when all attempts return refusal-shaped JSON. The
runner then only learns about refusal via the exception, not via tagged
tuples and not via a new `tuple[list[OcrPageResult], list[bool]]` return on
`_ocr_all_pages`. Under this alternative:

- `_make_default_ocr_fn(config, prompt_index)` and the per-attempt closure
  rebuild in `_ocr_one_page` are unnecessary; the cycling lives where the
  prompt actually lives — in the function that invokes `codex exec`.
- The plan's structured collector (`("ok", page, result)` vs.
  `("needs_review", page, result)`) collapses to a `try/except OcrRefusalExhausted`
  in `_ocr_one_page`, which is the same shape Python already gives you for
  every other "subprocess can fail or succeed" boundary.
- The seam `Callable[[Path], OcrPageResult]` becomes
  `Callable[[Path], OcrPageResult]` that may raise `OcrRefusalExhausted` —
  test injection becomes "raise the exception to simulate exhausted retries,"
  which is one mock line, not a per-page `side_effect` list of 3 refusals.

The cost of this alternative is non-trivial and is why I am presenting it as
antithesis rather than as a counter-recommendation: it (a) buries a piece of
Prepare policy (the 3-attempt count) inside a boundary helper, (b) makes the
sentinel-on-exhaustion behavior less directly visible at the runner level
where the `needs_review` flag is constructed, and (c) couples test injection
to an exception type rather than to return values. The plan rejects this
implicitly in its Principles bullet ("the retry loop lives at the runner
seam, not inside `run_codex_ocr`"), and the rejection is defensible — but it
is not argued in the plan. The Planner should either justify the
runner-side placement with one or two sentences (the "policy stays
co-located with the sentinel-emission decision" argument is the strongest),
or accept the antithesis. Right now the plan reads as if there were no
choice to make at this layer.

---

## 2. Tradeoff tensions

### 2.1 Tension: structured-collector return tuple vs. exception flow

*On one side:* the plan's tagged-tuple collector
(`("ok"|"needs_review", page, OcrPageResult)`) and the new
`_ocr_all_pages(...) -> tuple[list[OcrPageResult], list[bool]]` return shape
make the "needs review" signal explicit and trivially testable: the worker
returns a tag, the collector splits by tag, the runner zips a parallel
`needs_review` list into `build_text_units(...)`. Every step is a pure
function over plain data.

*On the other:* the runner now has two parallel lists of length
`len(rasterized)` (`ocr_results` and `needs_review_flags`) that must stay
1-indexed-aligned forever, plus the `_assert_page_alignment` check in
`text_units.py` has to grow a third length-equality assertion. The
"three parallel lists that must stay aligned" smell is exactly the smell the
1-indexed-vs-0-indexed convention in `text_units.py:14-19` was designed to
contain. Adding a third sibling array doubles the surface area where an
off-by-one can occur (collector sort, list ordering, build_text_units zip).

*Plan currently picks:* tagged tuples + parallel `list[bool]` (D4 + structured
collector). The plan is explicit about this and the `strict=True` zip in
`text_units.py` plus the new length assertion are intended to catch
misalignment at construction time.

*What would change my mind:* if the plan instead carried the `needs_review`
flag on a richer return type from `_ocr_one_page` (e.g. a small
`@dataclass(frozen=True)` `_OcrPageOutcome(page: int, result: OcrPageResult,
needs_review: bool)`) and `_ocr_all_pages` returned
`list[_OcrPageOutcome]`, the parallel-lists smell goes away entirely.
`build_text_units` could then take `list[_OcrPageOutcome]` directly (or be
called with `[outcome.needs_review for outcome in outcomes]` extracted at
exactly one site). This is **not** a contract change — `_OcrPageOutcome` is
runner-internal. It is a cheap fix to the parallel-array smell that
preserves every locked input.

### 2.2 Tension: `OCR_PROMPTS: tuple[str, str, str]` as policy-in-code vs. as configuration

*On one side:* the three escalation strings are encoded as a module constant
in `prompts.py`. That is the simplest thing that works, it makes the prompt
text reviewable in git, and locked input #2 explicitly pins this shape.

*On the other:* "constants in a module" is exactly how prompt iteration
costs accumulate — every prompt tweak becomes a code change that flows
through code review, CI, and a deployment. For a system whose primary
unknown is "what wording does the model accept?", this is a slow feedback
loop. The plan acknowledges this as out-of-scope ("No CLI knobs"), which is
correct for Step 1.1, but the plan does not flag that **the three-prompt
shape is itself a hypothesis** — there is exactly zero empirical evidence in
the plan that prompt indices 1 and 2 actually unstick the 5 historical
refusals. The plan treats "escalation works" as given.

*Plan currently picks:* hardcoded constants, no empirical verification of
the escalation prompts.

*What would change my mind:* one bullet under "Open questions" or under the
Manual recovery test that says explicitly: "if the manual recovery test
shows `review_count == 5` (all five refusals survived all three prompt
variants), the escalation strings need re-tuning before we declare success."
Right now Open Question #1 captures a different concern (sentinel
overuse), and the plan implicitly assumes the prompts work. They might not.

### 2.3 Tension: silent additive contract change vs. visible schema bump

*On one side:* `needs_review: bool = False` is additive, optional, has a
safe default, and Step 1 has no deployed consumers yet (the slice just
landed on this branch and has not been released). The ADR's
"`schema_version` stays at `1`" argument is internally consistent and is
explicitly locked input #6.

*On the other:* this is — by the plan's own admission — a contract change
that any future consumer that pins `extra="forbid"` and a frozen local copy
of the model could break on. The plan covers itself with "no such pinned
consumer exists yet in-repo," which is true today and which I verified
(`PreparedTextUnit` has exactly one definition at `contracts.py:14`). But
the precedent matters: the **next** additive optional field will face the
same argument ("there is no pinned consumer yet"), and the one after that,
and at some point a consumer pins and breaks. Locking the `schema_version`
discipline now ("any field change bumps the version") is a strictly safer
rule than "additive defaults are free." The plan rejects this discipline.

*Plan currently picks:* additive-without-version-bump.

*What would change my mind:* the plan adds **one** explicit sentence to the
ADR's `schema_version` section: "this exemption applies because Step 1 has
zero downstream consumers at commit `c6d387f`; any contract change after
the first Transform-stage consumer lands MUST bump `schema_version` even if
additive." That sentence converts a one-off decision into a documented
policy that the next slice planner can follow. Without it, the plan is
implicitly arguing "additive-with-default is always free," which it isn't.

---

## 3. Synthesis (where viable without violating locked input)

For 2.1: adopt the `_OcrPageOutcome` dataclass-internal-to-runner synthesis.
This preserves every locked input (3 attempts, prompts tuple, regex anchor,
seam shape, additive contract field, no validator change) and eliminates the
parallel-lists smell at zero structural cost. It is purely a Step-1.1
implementation refinement, not a contract change. The Critic should require
this.

For 2.2: add one open-question bullet that flags "the escalation prompts are
a hypothesis; the manual recovery test verifies it." Locked input #10 ("no
CLI knobs") is preserved — this is documentation, not a code change.

For 2.3: add the one-sentence policy clarification to the ADR. Locked input
#6 ("schema_version stays at 1") is preserved — this clarifies *why* the
exemption applies and bounds future use.

For the steelman antithesis itself (§1): I do not propose synthesis. The
plan's choice (retry-in-runner) is the right one **if** it is argued. The
Planner needs to add one or two sentences justifying "policy stays
co-located with the sentinel-emission decision." If they do, antithesis
collapses.

---

## 4. Principle-violation flags

### 4.1 AGENTS.md "Code Rules" — "Do not add empty runners, ports, adapters, or services until a later slice has real orchestration or external-boundary behavior to represent."

The plan introduces:

- `_ocr_attempt(...)` (`runner.py`, new private helper)
- `_make_default_ocr_fn(config, prompt_index)` (`runner.py`, new private builder)
- `_looks_like_refusal(transcript)` (`ocr.py`, new free function)

`_ocr_attempt(...)` is, by the plan's own admission, "a thin one-liner that
calls `ocr_fn(page_image)`" (plan line 192, "Simpler executor framing"). A
one-liner that wraps a single function call **with no additional behavior**
is the textbook empty-adapter smell. Locked input #4 pins the seam shape
`Callable[[Path], OcrPageResult]`, which means `_ocr_attempt` adds zero
behavior on top of `ocr_fn(page_image)`. **Severity: medium.** This is the
single biggest principle violation in the plan.

`_make_default_ocr_fn(config, prompt_index)` is a different case. It
**does** carry behavior: it parameterizes `prompt` by attempt index, and
`partial(run_codex_ocr, ..., prompt=OCR_PROMPTS[prompt_index])` is the
concrete behavior. This is a legitimate builder — keep it. **Severity:
none.**

`_looks_like_refusal(transcript)` carries the compiled regex constant and
the anchored-prefix logic — it is concrete behavior, not an empty function.
**Severity: none.**

**Fix:** remove `_ocr_attempt(...)` entirely. The plan even concedes this in
its "Simpler executor framing" paragraph: the worker should call
`per_attempt_ocr_fn = _make_default_ocr_fn(config, attempt_index)` directly
when the runtime builds it, and call the test-injected `ocr_fn` directly
when the test injects one. There is no remaining responsibility for
`_ocr_attempt` to hold. Delete it.

### 4.2 AGENTS.md "Boundaries" — `stages/prepare/` widened scope

Step 1 widened `stages/prepare/` to permit "a runner, a `python -m`-style
CLI, PDF rasterization, one OCR prompt string, and plain module-level seam
functions." The plan's additions (`OCR_PROMPTS` constant, `_looks_like_refusal`
free function, `_make_default_ocr_fn` builder, `needs_review` flag) are all
inside that widened scope. **No violation.**

### 4.3 CLAUDE.md "Contract Changes" protocol — full reference set update

The protocol requires: `docs/lnvo/` reference page **+** Pydantic contract
model **+** validator or round-trip tests **+** package `CONTEXT.md` only
when local vocabulary changes.

- `docs/lnvo/01-prepare.md` — plan adds the new row (line 130) and the
  semantics sentence (line 137). **Covered.**
- Pydantic contract model `contracts.py` — plan adds
  `needs_review: bool = False` (diff at line 114). **Covered.**
- Validator or **round-trip test** — locked input #14 forbids a new
  validator check. The plan covers the round-trip requirement by adding the
  `prepared.text_units[0].needs_review is True` assertion *plus*
  `PreparedVolume.model_validate_json(...)` round-trip in
  `test_runner_retry.py::retry_exhausted` (plan line 346). The existing
  end-to-end test (`test_runner_end_to_end.py:42-44`) already round-trips a
  `PreparedVolume` and the plan adds the
  `[unit.needs_review for unit in prepared.text_units] == [False] * N`
  assertion (plan line 282) so the new field is exercised on the happy
  path too. **Covered.**
- Package `CONTEXT.md` — the plan explicitly argues no update is needed
  (no new local vocabulary term). I verified this against `AGENTS.md` and
  `contracts.py`: `needs_review` is self-describing, not a new artifact
  path, stage name, or enum value. **Correctly skipped.**

**One gap I want flagged explicitly:** the plan does not propose a direct
unit-test on the contract itself — i.e. a `test_contracts.py` (or extension
of one if it exists) that asserts
`PreparedTextUnit.model_validate_json('{"text_unit_id": "...", "order": 0,
"text": "...", "source_path": "...", "source_locator": {}}')` succeeds (no
`needs_review` key → default `False`) **and** that an unknown key like
`"needs_revue": true` still raises under `extra="forbid"`. The round-trip
through `test_runner_retry.py` exercises this implicitly, but a direct
contract-level test pins the back-compat claim in the ADR (lines 77–79) to
a CI-enforced invariant. **Severity: low.** Add one targeted contract test
or note explicitly why round-trip-via-runner is sufficient.

### 4.4 Pydantic `extra="forbid"` semantics

`ContractModel` is configured `frozen=True, extra="forbid"` at
`common/artifacts.py:16`. Pydantic v2 `extra="forbid"` rejects **unknown
keys** during validation; it does **not** reject **missing keys that have
defaults**. So
`PreparedTextUnit.model_validate_json('{"text_unit_id": "unit_000000",
"order": 0, "text": "x", "source_path": "source/pages/001.png",
"source_locator": {}}')` will succeed under the new model and yield
`needs_review=False`. This matches the plan's "new reader, old artifact"
claim at line 79. **No violation.**

One subtlety the plan correctly handles: the model is `frozen=True`, which
means `needs_review` cannot be mutated post-construction. Since the runner
constructs `PreparedTextUnit` once at `build_text_units` time and never
mutates it, this is fine.

### 4.5 Anchor + 1-indexed-page-vs-0-indexed-order convention

`text_units.py:14-19` pins: filesystem `page` is 1-indexed; `order` and
`text_unit_id` integer suffix are 0-indexed. The plan's new third positional
parameter `needs_review: tuple[bool, ...]` is required to be 1-indexed-aligned
with `rasterized` (plan line 246). The plan extends `_assert_page_alignment`
to enforce `len(needs_review) == len(rasterized)`. **The 1-indexed-vs-0-indexed
convention is preserved.** No violation.

### 4.6 `is_illustration` semantic (user explicitly fixed in Step 1)

The plan's sentinel emits `is_illustration=False` on exhaustion (plan line
206). It does **not** re-open the illustration-narrowing question. The new
test cases also do not touch the illustration verdict. **No violation.**

However, **Open Question #1 in the plan is real and load-bearing**: the
third escalation prompt instructs the model to return
`{"transcript": "", "is_illustration": false}` on refusal, which **could**
get used by the model on legitimately-empty pages too. The plan defers
mitigation, which is acceptable for Step 1.1, but the Critic should track
this — if mitigation becomes necessary, the obvious fix is to flag
`(transcript == "" and is_illustration is False)` as `needs_review=True` in
the runner. That mitigation is **not** in scope here.

### 4.7 Locked input verification

I cross-checked all 14 locked-input items against the plan:

1. 3 total attempts, no CLI knob → plan line 33 (A4-chosen) and line 189
   (`_OCR_MAX_ATTEMPTS: Final[int] = 3`). **Honored.**
2. `OCR_PROMPTS: tuple[str, str, str]` with exact additional text → plan
   line 38 (B3-chosen) and lines 155–164 (verbatim escalation text).
   **Honored.**
3. Anchored regex on `transcript.lstrip()[:120]`, case-insensitive, exact
   phrase list → plan lines 168–180. **Honored.**
4. Retry loop inside `_ocr_one_page`, seam stays
   `Callable[[Path], OcrPageResult]` → plan lines 14, 192, 200. **Honored.**
5. Don't-abort; collect ok / needs_review per future; semantic refusals
   never raise; other exceptions still abort → plan lines 204–212.
   **Honored.**
6. `needs_review: bool = False` on `PreparedTextUnit`, additive optional,
   schema_version 1 → plan lines 105–117, 77–80. **Honored.**
7. Cached refusal JSONs → cache miss with WARNING line → plan lines 55,
   207–210. **Honored.**
8. No CLI knobs, no new deps → plan lines 17, 70 ("Out of scope"); only
   stdlib `re`/`logging`/`concurrent.futures`/`functools`. **Honored.**
9. Branch `feat/lnvo-v2-prepare-step1` → plan line 5 ("HEAD `c6d387f`").
   **Honored.**
10. `is_illustration` rule untouched → plan does not alter the rule.
    **Honored.**
11. No validator change → plan line 231 explicitly states "The
    `validate_prepared_volume(...)` call is unchanged. Locked input #14
    explicitly forbids a new validator check for `needs_review`."
    **Honored.**

**All locked inputs are honored.** Nothing I propose contradicts them.

---

## 5. Verdict and required revisions

`ITERATE` — the plan is structurally close to correct, all 14 locked inputs
are honored, and the Pydantic and back-compat reasoning is sound. The
blocking issues are: one empty-helper violation that the plan itself
already admits is a one-liner; one parallel-arrays smell that has a clean
internal-dataclass fix; and a small documentation gap around the
`schema_version` exemption and the prompt-escalation hypothesis. These are
revisions, not redesigns.

**Required revisions before Critic acceptance (atomic, in order):**

1. **Delete `_ocr_attempt(...)`.** The "Simpler executor framing"
   paragraph at plan line 192 already concedes this is a one-liner over
   `ocr_fn(page_image)`. Remove it from the file-level change list and
   from the ADR. The worker calls
   `per_attempt_ocr_fn = _make_default_ocr_fn(config, attempt_index)` (or
   the test-injected `ocr_fn`) and invokes it directly.

2. **Replace the parallel `list[OcrPageResult]` + `list[bool]` return of
   `_ocr_all_pages` with `list[_OcrPageOutcome]`,** where
   `_OcrPageOutcome` is a runner-private `@dataclass(frozen=True)`
   carrying `(page: int, result: OcrPageResult, needs_review: bool)`.
   `build_text_units(...)` then extracts the `needs_review` tuple at
   exactly one call site in `run_prepare`. The contract field stays
   `needs_review: bool = False` and the third positional parameter on
   `build_text_units` stays `needs_review: tuple[bool, ...]` — only
   the runner-internal plumbing changes.

3. **Add one sentence to the ADR justifying retry-in-runner over
   retry-in-`run_codex_ocr`.** Something like: "The retry loop lives in
   `runner.py` so prompt-cycling policy stays co-located with the
   sentinel-emission decision and the `needs_review` flag construction.
   `run_codex_ocr` stays a single-attempt boundary function." This
   directly answers the steelman antithesis above.

4. **Add one sentence to the ADR `schema_version` rationale (lines
   77–80) bounding the exemption.** Suggested wording: "This
   additive-without-bump exemption is justified because Step 1 has zero
   downstream consumers at commit `c6d387f`. Any contract change after
   the first Transform-stage consumer lands MUST bump `schema_version`
   regardless of whether the change is purely additive."

5. **Add one bullet under "Open questions" flagging that the prompt
   escalation itself is a hypothesis.** Suggested wording: "The three
   escalation prompts (`OCR_PROMPTS[0..2]`) are not empirically
   validated against the 5 historical refusals; the manual recovery
   test is the first real-world verification. If `review_count == 5`
   survives the recovery test, the prompts need re-tuning before this
   slice is declared shipped."

6. **Add one direct contract-level test for `needs_review`.** A test in
   `tests/automations/ln_voice_over_v2/stages/prepare/` that asserts
   (a) `PreparedTextUnit.model_validate_json(...)` succeeds when
   `needs_review` is omitted and yields the `False` default, and (b)
   passing an unknown key (e.g. `"needs_revue": true`) still raises
   under `extra="forbid"`. This pins the back-compat claim in ADR
   lines 77–79 to CI.

7. **Optional but recommended:** add the `(transcript == "" and
   is_illustration is False)` sentinel-overuse mitigation to Open
   Question #1 as a concrete deferred follow-up rather than free-form
   prose. This is the only realistic mitigation if the third
   escalation prompt bleeds into legitimate empty pages.

If revisions 1–6 are applied, the plan is `APPROVE`-ready. Revision 7 is
recommended-but-not-blocking.

---

## References

- `automations/ln_voice_over_v2/AGENTS.md:43-47` — "Do not add empty
  runners, ports, adapters, or services until a later slice has real
  orchestration or external-boundary behavior to represent." Basis for §4.1.
- `automations/ln_voice_over_v2/AGENTS.md:31-37` — Prepare-stage scope
  widening (free functions, no Protocols/ports). Basis for §4.2.
- `automations/ln_voice_over_v2/common/artifacts.py:13-17` —
  `ContractModel` config `frozen=True, extra="forbid"`. Basis for §4.4.
- `automations/ln_voice_over_v2/stages/prepare/contracts.py:14-21` — current
  `PreparedTextUnit` shape; confirms additive `needs_review: bool = False`
  is the minimum diff.
- `automations/ln_voice_over_v2/stages/prepare/ocr.py:12,15-21,30` — current
  `OCR_PROMPT` default-arg sentinel and `OcrPageResult`'s `extra="forbid"`
  config. Confirms the `OCR_PROMPT = OCR_PROMPTS[0]` alias keeps
  `run_codex_ocr(prompt=OCR_PROMPT)` resolving at import time.
- `automations/ln_voice_over_v2/stages/prepare/runner.py:108,121,140-157` —
  current `_ocr_all_pages` shape (single `list[OcrPageResult]` return) and
  the single `build_text_units(ocr_results, rasterized)` call site.
  Basis for §2.1 and the §5 revision 2 (internal-dataclass synthesis).
- `automations/ln_voice_over_v2/stages/prepare/runner.py:160-180` — current
  `_ocr_one_page` worker; this is the file the retry loop lives in.
- `automations/ln_voice_over_v2/stages/prepare/text_units.py:10-47` —
  current `build_text_units` signature and `_assert_page_alignment`. Basis
  for the 1-indexed-vs-0-indexed verification in §4.5.
- `automations/ln_voice_over_v2/stages/prepare/validation.py:12-76` — the
  validator's invariants. Confirms locked input #14: no `needs_review`
  reference, no new check.
- `automations/ln_voice_over_v2/stages/prepare/prompts.py:10-27` — current
  single `OCR_PROMPT`; the locked-input prompt text is being kept as
  `OCR_PROMPTS[0]` verbatim.
- `docs/lnvo/01-prepare.md:49-69` — current Prepared Text Unit table; the
  plan correctly appends one row at line 130 of the plan.
- `tests/automations/ln_voice_over_v2/stages/prepare/test_runner_end_to_end.py:42-58,97-101`
  — current fixture shape (2-page PDF, `fake_ocr_fn` dispatches by page
  number). Confirms the plan's reuse strategy and the 3-page fixture
  extension is feasible.
- `tests/automations/ln_voice_over_v2/stages/prepare/test_text_units.py:25,49-50`
  — current `build_text_units` call sites; the plan's third-positional
  parameter change requires updating exactly these call sites.

VERDICT: ITERATE — 6 atomic revisions required, 1 optional.

## Iteration 2 — re-review of revised plan

verdict: ITERATE
timestamp: 2026-05-26T01:00:00Z

I re-read the revised plan in full (`.omc/plans/lnvo-v2-prepare-step1.1-hardening.md`, lines 1-606), plus the contract-index, `common/enums.py` (`ReviewStatus` at lines 18-22), and the package `CONTEXT.md`, to verify the merged revisions in context.

### 1. Status of round-1 revisions

| # | Round-1 ask | Status | Where / rationale |
|---|---|---|---|
| 1 | Delete `_ocr_attempt(...)` | Resolved | Plan line 231: "No `_ocr_attempt` wrapper." Runner invokes per-attempt `ocr_fn` directly. No dangling references. |
| 2 | Replace parallel lists with `_OcrPageOutcome` | Resolved | Plan lines 215-223 declare the frozen private dataclass; lines 248-259, 266-272 thread it end-to-end. Coherent. |
| 3 | ADR sentence justifying retry-in-runner | Resolved | Plan line 76 ("Why retry-in-runner...") gives three-pointed rationale. |
| 4 | Bound `schema_version` exemption | Resolved | Plan line 89 scopes the waiver to "Step 1 has zero downstream consumers at commit c6d387f"; any change after first Transform consumer MUST bump. |
| 5 | Flag prompt escalation as hypothesis | Resolved | Plan line 579 (Open Question #1): the manual recovery test is the first real-world verification. |
| 6 | Contract-level back-compat tests | Resolved | Plan lines 460-489 declare `test_contracts.py` with the three named tests. |
| 7 (optional) | Sentinel-overuse mitigation concrete | Resolved | Plan line 580 (Open Question #2): C2 fix flags `(transcript="", is_illustration=False)` as `needs_review=True`. |

All 6 required + 1 optional revision are resolved.

### 2. Newly-required principle re-checks

- `_is_failed_ocr` covers both shapes (regex prefix + structural sentinel) on both paths (attempt loop + cache hit). Plan lines 201-204, 235-245.
- `_ocr_attempt` wrapper is gone; no leftover references.
- `_OcrPageOutcome` replaces parallel/discriminator pattern coherently end-to-end.
- `bool needs_review` justified in ADR with four-sentence argument citing canonical idiom at `stages/dialogue/contracts.py:38` and `stages/scenes/contracts.py:80`.
- `extra="forbid"` round-trip preserved; plan lines 86-87 cover both directions; back-compat tests pin to CI.
- Atomic-commit ordering subsection coherent with CLAUDE.md Contract Changes protocol.
- `docs/lnvo/contracts-index.md` no-update justified (artifact-level rows only; new field is sub-row).
- No touch of `common/*`, `pipeline/`, `series/`, or other `stages/*/contracts.py`.
- `is_illustration` rule preserved in three independent places.

### 3. Newly-introduced issues

1. **(BLOCKING) `_is_failed_ocr` matrix internal contradiction at plan line 386.** The whitespace-only `"   "` row has its Expected column set to `True`, but the prose body of the same cell locks resolution **(a) → return `False`**. The Expected column must read `False` and the Reason cell must match the locked decision: "After `lstrip()` the prefix is empty so the regex branch returns `False`; the structural-sentinel branch needs `transcript == \"\"` exactly, which `\"   \"` does not satisfy. Whitespace-only on a non-illustration page is treated as a degenerate real success, not a failure." This is the only freshly-introduced bug; the matrix is the implementer's test spec, so the contradiction is load-bearing.

2. (low / cosmetic) Documentation drift in `docs/lnvo/01-prepare.md` example JSON — plan already covers via prose at line 145; accept.

3. (low / cosmetic) Plan line 200 says `_looks_like_refusal` is "importable by `runner.py`" but the revised design has only `_is_failed_ocr` imported into the runner. Update wording to "importable by the test module."

4. (cosmetic) "Atomic-commit ordering" at plan line 156 is more accurately "Atomic commit grouping."

5. (deferrable) Open Question #1 lacks a concrete "if escalation fails after both `--workers 8` and `--workers 4` runs" stop condition. Genuine post-recovery deferral.

### 4. Locked input verification

All 14 locked-input items remain honored after iteration 2. Highlights: `_OCR_MAX_ATTEMPTS: Final[int] = 3` (line 213); `OCR_PROMPTS` exact escalation text (lines 170-181); regex on `transcript.lstrip()[:120]` (lines 186-199); retry inside `_ocr_one_page` with `Callable[[Path], OcrPageResult]` seam (line 234); semantic refusals never raise (line 246); `needs_review: bool = False` additive optional with `schema_version=1` (lines 122-123, 85-89); cached failure JSONs treated as cache miss with WARNING (line 238); no CLI knobs / no new deps (line 18); branch `feat/lnvo-v2-prepare-step1` (line 5); `is_illustration` rule untouched (verified at three sites); no validator change (line 274).

No iteration-2 revision contradicts any locked input.

### 5. Verdict

`ITERATE` — one load-bearing matrix inconsistency (whitespace-only row at line 386, Expected column wrong) blocks acceptance. Issues 2-5 are cosmetic / deferrable.

**Required revision (R1, blocking):** Fix the matrix row at plan line 386. Change Expected `_is_failed_ocr` column from `True` to `False`, and trim Reason to match the locked decision: "After `lstrip()` the prefix is empty so the regex branch returns `False`; the structural-sentinel branch needs `transcript == \"\"` exactly, which `\"   \"` does not satisfy. `_is_failed_ocr` does NOT normalize whitespace beyond `_looks_like_refusal`'s internal `lstrip`. Whitespace-only on a non-illustration page is treated as a degenerate real success, not a failure."

**Recommended (non-blocking):**
- R2: Update plan line 200 from "importable by `runner.py` and by the test module" to "importable by the test module."
- R3 (cosmetic): Rename "Atomic-commit ordering" at line 156 to "Atomic commit grouping" or "Atomic commit boundary."
- R4 (deferrable): Add an "escalation-prompt-retune trigger" sentence to Open Question #1 at line 579.

If R1 is applied, the plan is APPROVE-ready.
