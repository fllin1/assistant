---
role: critic
target_plan: lnvo-v2-prepare-step1.1-hardening.md
target_architect_review: lnvo-v2-prepare-step1.1-hardening.architect.md
timestamp: 2026-05-26T00:00:00Z
verdict: ITERATE
---

# Critic Review — LNVO v2 Step 1.1 (Prepare Hardening)

## Verdict at a glance

**ITERATE.** All 14 locked inputs are honored. Pydantic / `extra="forbid"`
reasoning is correct. The historical-refusal regex matches the 5 pinned strings
under `lstrip()[:120]` case-insensitive anchored match. But the plan ships with
**one CRITICAL package-vocabulary collision**, **two MAJOR structural smells the
architect already flagged**, and **two MAJOR specification gaps the architect
missed** that materially affect the implementer's task. None are redesigns —
all are atomic edits.

---

## Pre-commitment predictions (recorded before structured verification)

I expected to find: (1) ambiguity around `_ocr_attempt` (empty-helper smell);
(2) parallel-array smell in `_ocr_all_pages`; (3) under-specified prompt-2
sentinel collision with truly-empty pages; (4) missing direct-contract test for
the new field; (5) some `schema_version` policy hand-waving; (6) a gap on
what concurrency does at 8 workers × 3 retries.

Actually found: predictions 1–6 confirmed. Plus **one prediction I did NOT make
and which is the biggest finding**: the package already has a `ReviewStatus`
enum at `common/enums.py:18-22` whose value `NEEDS_REVIEW = "needs_review"` is
listed in `docs/lnvo/contracts-index.md:12` under "Shared Rules." The plan adds
a plain `bool needs_review` field that creates a parallel idiom for "this row
needs review" alongside the canonical `status: ReviewStatus` pattern used by
`DialogueChapter` (`stages/dialogue/contracts.py:38`) and `SceneDocument`
(`stages/scenes/contracts.py:80`). This is package-vocabulary drift that the
architect did not flag.

---

## Critical findings (block ITERATE → APPROVE until resolved)

### C1. Parallel "needs review" idiom collides with existing `ReviewStatus` enum

**Evidence.**
- `automations/ln_voice_over_v2/common/enums.py:18-22` defines
  `class ReviewStatus(StrEnum): ACCEPTED = "accepted"; NEEDS_REVIEW = "needs_review"`.
- `automations/ln_voice_over_v2/stages/dialogue/contracts.py:38`
  uses `status: ReviewStatus` on `Dialogue`.
- `automations/ln_voice_over_v2/stages/scenes/contracts.py:80`
  uses `status: ReviewStatus` on `Beat`.
- `docs/lnvo/contracts-index.md:12` lists
  `Review status | "accepted", "needs_review"` as a **Shared Rule**.
- Plan line 114 introduces `needs_review: bool = False` on
  `PreparedTextUnit` — a **different** idiom for the same concept.

**Why this matters.** The Shared Rules table in `contracts-index.md` is the
single canonical place a downstream reader looks to learn how the package
represents "needs review." Adding a `bool needs_review` on
`PreparedTextUnit` creates a second representation for the same semantic
concept that the package's own contracts-index does not list. A future
Transform-stage reader checking `prepared.text_units[i].status` (the
natural next idiom, mirroring `Dialogue.status` and `Beat.status`) finds
nothing, and the package has two ways to say the same thing.

**Confidence.** HIGH. The plan and architect review both missed this. The
locked-input brief permits `needs_review: bool = False`; that locks the
**field name**, but the **type choice** (`bool` vs.
`status: ReviewStatus = ReviewStatus.ACCEPTED`) is implementer scope and
the bool choice fights existing package vocabulary.

**Fix (recommended path).** The locked input pins the field name
`needs_review` and a `bool` default of `False`. If the user truly wants
`bool`, the plan MUST add a one-sentence ADR justification explicitly
addressing why `PreparedTextUnit` deviates from the
`status: ReviewStatus` idiom used by `Dialogue` and `Beat`. Suggested
ADR sentence: "`PreparedTextUnit` uses a plain `bool needs_review`
rather than the package's `status: ReviewStatus` enum because Prepare
emits no graded review statuses (no `revised`, no `manual_override`,
etc.) — only a binary 'OCR retry budget exhausted' signal — and a bool
keeps the artifact one-key-narrower without losing information." If the
user has not actually locked `bool` (the brief lists the field as
`needs_review: bool = False`, which **does** lock both), this finding
escalates to "switch to `status: ReviewStatus`." Confirm with user
before resolving.

**Realist check.** This is **not** a runtime bug; both representations
parse and validate. But it is a contract-design tax that will
compound. **Mitigated by:** the field is new; no other contract reads
it yet; if Step 2 (Transform) is the first reader, it can be aligned in
the Step 2 plan. **Final severity: CRITICAL for plan revision
(documentation), but the underlying field-type decision may stay `bool`
if explicitly justified.**

### C2. Empty-prompt-3 transcript collides with the runner's refusal-or-success classifier

**Evidence.**
- Plan lines 160–163 instruct the model in `OCR_PROMPTS[2]` to return
  exactly `{"transcript": "", "is_illustration": false}` on refusal.
- Plan lines 204–206 detect refusal via
  `_looks_like_refusal(result.transcript)`. An empty string does NOT
  match `_REFUSAL_PREFIX_RE` (no `i can't`, no `sorry`, no `as an ai`).
- Therefore the runner treats `{"transcript": "", "is_illustration": false}`
  on attempt 3 as a **success**. The resulting `PreparedTextUnit` has
  `text=""` and `needs_review=False`.
- Plan Open Question #1 (lines 452) *acknowledges* this collision but
  defers mitigation.

**Why this matters.** This is the **happy path for a refused page on
attempt 3** under prompt 2's wording. The runner's whole purpose is to
mark refusal-survivor pages `needs_review=True`. Under the plan as
written, the most-prompted attempt yields exactly the sentinel shape
the runner would have constructed on exhaustion — but with
`needs_review=False`, silently losing the operational signal. The
architect review caught this and proposed the right mitigation in §4.6;
the plan defers it to "if observed." That is the wrong default. The
mitigation costs one `if` branch in the runner.

**Confidence.** HIGH. Verified by reading plan line 178 ("`_looks_like_refusal`
returns truthy only on `_REFUSAL_PREFIX_RE.match(...)`") against plan line 163
("return exactly the JSON `{\"transcript\": \"\", \"is_illustration\": false}`").
No `i can't` prefix, no match.

**Fix.** Plan must reconcile this **before** Codex implementation, not after
the first run reveals silent loss. Concrete reconciliation (pick one and
state it explicitly):
- **(a) Treat the sentinel-shaped success as refusal-on-the-current-attempt.**
  Detect `(transcript == "" and is_illustration is False)` in the runner
  alongside `_looks_like_refusal(transcript)`. If both predicates miss,
  it's a real success; if either hits, it's a refusal-style attempt. On
  attempt 3, both lead to the sentinel emission with `needs_review=True`.
  This is the architect's §4.6 proposal and the Open Question #1 deferred
  mitigation. Make it not-deferred.
- **(b) Accept the sentinel-shaped response as a legitimate "model
  declined" and use attempt-index alone to assign `needs_review`.** If
  attempt 3 returned anything (refusal-shaped, sentinel-shaped, or
  ordinary), and the previous attempts also failed, mark
  `needs_review=True` based on having reached attempt 3, regardless of
  the final transcript shape. Simpler but slightly less precise (a real
  empty page reached on attempt 3 would also get flagged — rare, but
  possible).

The plan must pick one and write the rule into the runner section
explicitly, not as a deferred Open Question.

**Realist check.** Worst case = a refused page from a real volume ships
into Transform with `needs_review=False` and empty `text`, looking
identical to a legitimately empty page. No detection signal for the
user. **Mitigated by:** the user inspects `review_count` after the
manual recovery test; if `review_count < expected`, they will notice.
But this depends on the user knowing the expected count and is brittle.
**Final severity: CRITICAL.**

---

## Major findings

### M1. `_ocr_attempt(...)` is an empty adapter

The architect already flagged this (§4.1). The plan itself (line 192,
"Simpler executor framing") concedes `_ocr_attempt` is a one-liner over
`ocr_fn(page_image)`. Delete it. The worker calls
`per_attempt_ocr_fn = _make_default_ocr_fn(config, attempt_index)` (or
the test-injected `ocr_fn`) directly. **Architect status: Unresolved
(planner has not yet revised).** **Confidence: HIGH.** **Severity: MAJOR.**
**Fix:** drop `_ocr_attempt` from the file-level change list, from the
ADR, and from §"_ocr_one_page rewrite."

### M2. Parallel `list[OcrPageResult]` + `list[bool]` return smell

The architect's §2.1 synthesis (introduce a runner-private
`@dataclass(frozen=True) _OcrPageOutcome(page: int, result: OcrPageResult,
needs_review: bool)`) eliminates the three-parallel-arrays smell at zero
contract cost. The plan currently returns
`tuple[list[OcrPageResult], list[bool]]` from `_ocr_all_pages` (plan line
218) and adds a third-positional `needs_review: tuple[bool, ...]` to
`build_text_units` (plan line 240). Both stay in spirit; only the
runner-internal collector changes from "two parallel lists" to "list of
records." **Architect status: Unresolved.** **Confidence: HIGH.**
**Severity: MAJOR.** **Fix:** adopt the dataclass synthesis exactly as
the architect described in §2.1 and §5 revision 2.

### M3. `build_text_units` third parameter — keyword-only vs. positional

The plan (line 244) explicitly chooses **required positional**. Rationale
given: "the existing two parameters are positional." This is defensible
but exposes a latent risk: a caller that calls
`build_text_units(ocr_results, rasterized)` in `run_prepare` (the current
single call site at `runner.py:121`) will fail with a clean
`TypeError: missing 1 required positional argument: 'needs_review'`.
Tests that currently call `build_text_units(ocr_results, rasterized)` at
`test_text_units.py:25, 49-50, 65` will also fail. The plan acknowledges
this in §"Updates to test_text_units.py" but does not flag the
**migration ordering**: if Codex applies the contract field, the
`build_text_units` signature change, and the runner unpack in the wrong
order, the tree is broken between commits. **Confidence: MEDIUM.**
**Severity: MAJOR.** **Fix:** add an explicit "Atomic-commit ordering"
subsection to the plan stating: contract change + `build_text_units`
signature change + runner unpack + test updates must land in a **single
commit**. No intermediate state where the tree is broken. This is a
one-paragraph addition.

### M4. Concurrency × retry blow-up — risk surfaced but not bounded

Plan Open Question #2 acknowledges 8 workers × 3 retries ≈ 24 in-flight
Codex calls in worst-case refusal-heavy batches. But this is the
**recovery test invocation** the user is going to run (plan line 408:
`--workers 8`). The plan does not pin a fallback: if rate-limit-adjacent
behavior bites on the first real recovery run, what is the user expected
to do — drop workers, retry, abort? Without a concrete fallback rule,
the manual recovery test could itself trigger refusals it is meant to
diagnose. **Confidence: MEDIUM.** **Severity: MAJOR.** **Fix:** add one
sentence under the manual recovery test: "If the first attempt at
`--workers 8` produces `review_count > 5` (i.e. more refusals than the
known historical 5), re-run with `--workers 4` to rule out
concurrency-induced rate-limiting before re-tuning prompts."

### M5. Missing direct contract-level back-compat test

The architect's §4.3 gap. The plan asserts in the ADR (lines 77–80) that
**old artifact + new reader yields `needs_review=False`** and that
**`extra="forbid"` correctly rejects unknown keys after the addition**.
Both claims are TRUE under Pydantic v2 (verified against
`common/artifacts.py:13-17` config `frozen=True, extra="forbid"`). But
neither is pinned by a direct unit test. The closest is the round-trip
inside `test_runner_retry.py::retry_exhausted` (plan line 346), which is
indirect. **Confidence: HIGH.** **Severity: MAJOR.** **Fix:** add one
test file `tests/automations/ln_voice_over_v2/stages/prepare/test_contracts.py`
(or extend an existing one if discovered at implementation time) with
two assertions: (a)
`PreparedTextUnit.model_validate_json('{"text_unit_id": "unit_000000", "order": 0, "text": "x", "source_path": "source/pages/001.png", "source_locator": {}}').needs_review is False`;
(b) parsing the same JSON with an extra key
`"needs_revue": true` raises `pydantic.ValidationError`. Names: e.g.
`test_prepared_text_unit_defaults_needs_review_false`,
`test_prepared_text_unit_rejects_unknown_key`.

### M6. Cache-sentinel resume semantics need an explicit one-liner

Locked input #9 (plan line 55, E3-chosen, plan line 210) says:
refusal-shaped cache entries → cache miss + WARNING + recompute. Good.
But: after a `retry_exhausted` run, the plan persists a **sentinel**
result `{"transcript": "", "is_illustration": false}` (plan line 206)
to `source/ocr/001.json`. On the **next** resume:
- `load_cached_ocr` parses it successfully (it is valid `OcrPageResult`
  shape).
- `_looks_like_refusal("")` is `False` (no refusal-prefix match on the
  empty string — verified by re-reading plan line 178).
- The runner treats the sentinel as a cache hit and returns
  `("ok", page, sentinel)` (plan line 211).
- But the sentinel was supposed to mean "this page never produced real
  OCR data." Treating it as `ok` and emitting `needs_review=False`
  silently downgrades the page from "needs review" to "definitely an
  empty page."

The plan does **not** address this. Architect's §4.6 is the same
mitigation as C2 above — flag `(transcript == "" and is_illustration is
False)` as needs_review in the runner. If C2 is fixed via path (a), M6
is auto-fixed. **Confidence: HIGH.** **Severity: MAJOR.** **Fix:** state
explicitly that the C2 mitigation also covers M6 (the sentinel-shape
detection runs on cache-hit too, not just on attempt-3 success).
Alternatively, persist a *marker* (e.g. write a side-car
`source/ocr/001.needs_review` empty file alongside `001.json`); but this
multiplies artifacts and is worse than fixing C2. Pick the C2-mitigation
path explicitly.

---

## Minor findings

### m1. Log levels for the two prepare-summary lines

Plan line 222 specifies `logger.warning(...)` for the per-page list and
`logger.info(...)` for the count summary. Good — both are pinned. The
user's brief asked me to confirm pinning; it is pinned. No change.

### m2. `automations/ln_voice_over_v2/CONTEXT.md` decision is stated

Plan lines 139–141 explicitly state no update is needed, with reasoning
("the field name `needs_review` carries its own meaning; the package's
local vocabulary is unchanged"). Acceptable, but **note**: if C1 is
resolved by adopting `ReviewStatus`, then `CONTEXT.md` still does not
need an update (the `ReviewStatus` term is already in the package). If
C1 is resolved by adding an ADR sentence justifying the bool, no
`CONTEXT.md` change either. **No change required.**

### m3. `docs/lnvo/contracts-index.md` decision

The plan does not explicitly state whether `contracts-index.md` needs an
update. **Verified independently:** `contracts-index.md` does not list
`PreparedTextUnit` row-level fields; it lists artifact-level rows and
shared rules. The new field on a sub-row does not change the artifact
map or shared rules. **No update needed** to `contracts-index.md`,
**but the plan should say so explicitly** (one sentence under
"Contract change scope (limited)"). **Severity: minor documentation
gap.**

### m4. The example JSON block in `01-prepare.md` is intentionally not updated

Plan line 133 chooses to keep the example clean (omission == false ==
default). This is the right call. No change.

### m5. Refusal regex prefix list is exhaustive against the 5 historical
strings only

The plan's regex covers `i can't`, `i cannot`, `i won't`, `i'm sorry`,
`i'm not able`, `sorry,? but`, `sorry,? i`, `as an ai`. Re-verifying
against the 5 historical strings (plan lines 304–308):
- `"Sorry, I can't provide..."` → matches `sorry,? i` (also `sorry,? but`
  would not match — there is no `but` after `sorry,`). Match.
- `"Sorry, I can't provide a full verbatim transcription..."` → same.
  Match.
- `"I can't provide a full OCR transcription..."` → matches `i can't`.
  Match.
- `"Sorry, I can't provide a full-page verbatim transcript..."` → matches
  `sorry,? i`. Match.
- `"Sorry, I can't provide a full verbatim OCR transcript..."` → matches
  `sorry,? i`. Match.

All 5 match. Good.

**However:** the plan does not explicitly call out that the
**curly-quote vs. straight-quote** distinction matters for regex
matching. The historical refusals use **straight ASCII apostrophe** `'`
in `can't`, `I'm`, etc. (verified by reading plan lines 304–308 in the
plan file as straight `'`). If `gpt-5.5` ever emits curly `'` (U+2019),
the regex misses. The plan's test embeds verbatim strings; the verbatim
strings as embedded in the plan use ASCII `'`. **Severity: minor.**
**Fix:** add one sentence to the refusal-detection section:
"Refusal-prefix regex matches straight ASCII apostrophe only; if a
future refusal arrives with curly `'`, extend the regex (out of scope
here)."

---

## What's missing (gap analysis)

- **G1.** No "atomic commit ordering" subsection (see M3).
- **G2.** No empirical-verification disclaimer on the escalation prompts
  themselves (architect §2.2 / revision 5). The plan treats prompt
  escalation as a settled hypothesis.
- **G3.** No `schema_version` exemption bound (architect §2.3 / revision
  4). The plan's ADR argues "no pinned consumer exists yet" but does
  not bound the exemption to this slice.
- **G4.** No direct `PreparedTextUnit` contract test (M5).
- **G5.** No retry-in-runner-vs-retry-in-`run_codex_ocr` justification
  (architect §1 steelman / revision 3).
- **G6.** No reconciliation between the sentinel-shaped attempt-3
  success and the refusal detector (C2, M6).
- **G7.** No ADR justification for `bool needs_review` instead of
  `status: ReviewStatus` (C1).
- **G8.** No explicit "contracts-index.md does not need updating"
  statement (m3).
- **G9.** No concurrency-fallback rule for the manual recovery test
  (M4).

## Ambiguity risks

- **A1.** Plan line 192 ("Simpler executor framing — preferred — adopt
  this if it is unambiguously achievable in code review"). →
  Interpretation A: keep `_ocr_attempt` as a wrapper; Interpretation B:
  drop it and inline. Risk if wrong interpretation chosen: dead helper
  (Interpretation A) vs. clean diff (Interpretation B). M1 forces B.
  Resolve in the plan.
- **A2.** Plan line 153 ("constructed by prefixing the current
  `OCR_PROMPT` body"). → Interpretation A: concatenate verbatim strings
  via `+`; Interpretation B: `f"{OCR_PROMPT}\n\n{ESCALATION_1}"` etc.
  Plan line 164 ("No f-string composition, no `.format()`, no
  `str.replace`") rules out B explicitly. Good — already
  disambiguated. **No change.**
- **A3.** Plan line 360 ("`caplog` contains exactly one `WARNING` line").
  → Interpretation A: the test asserts `==1` count of refusal-WARNING
  lines; Interpretation B: the test asserts at least one. Plan says
  "exactly one." Implementer must use a precise filter (
  `[r for r in caplog.records if r.levelname == "WARNING" and "refusal-style" in r.message]`
  ) and `len == 1`. Plan should pin the assertion shape. **Severity:
  minor.**

---

## Plan-section-by-locked-input compliance matrix

| Locked input | Realized at | Status |
| --- | --- | --- |
| 3 attempts total, no CLI knob | plan line 33, 189 (`_OCR_MAX_ATTEMPTS = 3`) | Honored |
| Exact escalation strings as separate `OCR_PROMPTS` tuple | lines 155–164 | Honored (verbatim) |
| Anchored regex `lstrip()[:120]` IGNORECASE on 7 prefixes | lines 168–180 | Honored — 8 prefixes listed because `sorry,? but` and `sorry,? i` count as one or two depending on count; verified against 5 historicals (m5). |
| Retry inside `_ocr_one_page`, seam `Callable[[Path], OcrPageResult]` | lines 14, 200 | Honored |
| ok/needs_review tuple return; refusals never raise; other exceptions still abort | lines 204–212 | Honored |
| `needs_review: bool = False` on `PreparedTextUnit`, additive optional, schema_version 1 | lines 105–117, 77–80 | Honored (but **see C1**) |
| Refusal cache → cache-miss + WARNING + recompute | lines 55, 207–210 | Honored |
| No CLI knobs, no new deps | lines 17, 70 | Honored |
| `feat/lnvo-v2-prepare-step1` HEAD `c6d387f` | line 5 | Honored |
| `is_illustration` rule untouched | plan does not alter it | Honored |
| No validator change | line 231 | Honored |

**All 14 locked inputs are met.** The blockers are scope-internal design
decisions, not locked-input violations.

---

## Architect-review revisions — current resolution status (planner has NOT yet revised)

1. **Delete `_ocr_attempt(...)`.** → **Unresolved** (still in plan lines
   190–192).
2. **Replace parallel-lists return with `_OcrPageOutcome` dataclass.** →
   **Unresolved** (plan still returns
   `tuple[list[OcrPageResult], list[bool]]` at line 218).
3. **Add ADR sentence justifying retry-in-runner.** → **Unresolved** (no
   such sentence; line 14 is the principle, but no ADR-level
   justification against the antithesis exists).
4. **Add ADR sentence bounding `schema_version` exemption.** →
   **Unresolved** (lines 77–80 argue the case but do not bound future
   slices).
5. **Add open-question bullet flagging prompt escalation as a
   hypothesis.** → **Unresolved** (Open Question #1 is a different
   concern; #2 is concurrency; #3 is i18n).
6. **Add direct contract-level test for `needs_review`.** →
   **Unresolved** (round-trip is indirect via runner test only).
7. **Optional: sentinel-overuse mitigation `(transcript == "" and
   is_illustration is False)`.** → **Partially-resolved** in Open
   Question #1 — but as a deferred mitigation, not a committed rule.
   **Per this review's C2, must be promoted from optional to required.**

---

## Multi-perspective notes

### Executor perspective

The plan as written tells the implementer to write code that has a known
silent-loss bug (C2). The implementer would either (a) write it as
described and silently regress refusal-on-attempt-3 cases or (b) notice
the collision while reading the runner section and ask for
clarification — losing one round-trip with the planner. The Codex task
brief should not require independent reasoning to find C2; it should be
written into the plan.

The plan is otherwise faithfully implementable in a single Codex sitting
once C2 and M3 (atomic-commit ordering) are pinned. The retry loop,
prompt builder, sentinel-emission, and structured collector are
implementer-grade specificity. The 5 test scenarios in
`test_runner_retry.py` are precise enough to write directly.

### Stakeholder perspective

The slice's promise is "one-shot completion of a real volume that the
user just lost a run to." That promise is met **only if** every refused
page that completes attempt 3 (in any shape — refusal text or
sentinel-shape) ends up with `needs_review=True`. Under the plan as
written, the sentinel-shape on attempt 3 silently drops the
`needs_review=True` signal. The stakeholder's "complete `prepared/volume.json`
in one invocation" is technically achieved (no abort) but the
user cannot route the surviving refusals without parsing transcripts by
hand — defeating one of the two stated decision drivers (line 22:
"Step 2 must be able to route refusal-survivor pages without re-parsing
transcripts"). **C2 is a driver-violation, not just a code smell.**

### Skeptic perspective

The strongest argument against this plan: **the three escalation
prompts are a bet, not an observation.** The plan has zero empirical
data that `OCR_PROMPTS[1]` and `OCR_PROMPTS[2]` actually move the model
off refusal. If the bet loses, the slice ships, the user re-runs, gets
`review_count == 5`, and the planner is back to square one with the
same 5 pages and a now-baked-in retry budget of 3. The slice **does**
recover the run completes (sentinels emitted), so the slice
fundamentally succeeds even if escalation fails — but the marketing
("auto-recoverable without deletion") is overclaimed.

This is the architect's §2.2 concern. Plan should hedge it explicitly
(revision 5).

---

## Verdict justification

**ITERATE.** The plan honors all 14 locked inputs and the Pydantic
back-compat reasoning is correct (verified against
`common/artifacts.py:13-17` `frozen=True, extra="forbid"`). The
regex matches all 5 historical refusals. The structural shape is
implementable. **But:** C1 (package-vocabulary collision with
`ReviewStatus`) is a finding the architect missed and a real future
tax; C2 (sentinel-shape vs. refusal-classifier collision) is a
driver-violation bug, not just a code smell; M1/M2/M5/M6 are unresolved
architect findings; M3 (atomic-commit ordering) and M4 (concurrency
fallback) and M5 (direct contract test) are MAJOR gaps the architect
missed.

The mode for this review stayed in **THOROUGH**. There is no CRITICAL
finding for a runtime bug that ships — C1 is contract-design drift
(documentation-fixable) and C2 is a known-silent-loss the plan defers
via Open Question #1; both warrant the CRITICAL label only against the
**plan**, not against the runtime. Realist Check: C1 stayed CRITICAL
because contract drift compounds across slices; downgrading it to
MAJOR would let the next slice inherit a precedent that future
review-status concepts also get bool fields instead of using the enum.
C2 stayed CRITICAL because the plan's own decision driver #2 (line 22)
is violated under prompt 2's wording; this is not theoretical, it is
the first refusal-on-attempt-3 case from the next real volume.
**Mitigated by: nothing — the silent-loss path is the happy path
under prompt 2 as written.**

No findings were downgraded by Realist Check. Self-Audit moved one
candidate (the "regex might miss `i shouldn't` prefix") to Open
Questions below.

---

## Open Questions (unscored)

1. Should `_REFUSAL_PREFIX_RE` also match `i shouldn't` / `i should not`?
   Not in the 5 historical strings; the model has not been observed
   using this phrasing. **Speculative — not a finding.**
2. Is there value in logging the **attempt index** alongside the
   final-result decision per page (e.g. `"prepare: page 172 OK on
   attempt 2"`)? This would give the user a refusal-rate signal across
   prompts without needing post-hoc analysis. **Nice-to-have — not a
   blocker.**
3. Should the cache-recompute log line include the historical refusal
   transcript text as evidence (truncated) so the user can grep for
   patterns? Probably useful, probably out of scope.
4. The `OCR_PROMPT = OCR_PROMPTS[0]` alias preserves the
   `ocr.py:12` import. But `ocr.py:30` also uses `OCR_PROMPT` as a
   default-arg sentinel for `run_codex_ocr`. That default-arg binding
   resolves at import time — when does Python rebind it after the
   alias is reassigned? Answer: it does not need to; the alias is set
   at module import once and `run_codex_ocr`'s signature default
   captures the value once. Verified. **Resolved, not a finding.**

---

## Merged revisions for the planner (in execution order)

Merging architect revisions (1–7) with this critic's findings (C1, C2,
M1–M6, m3, m5) and de-duplicating. Each item is atomic, action-verb-led,
and names a target plan section.

1. **Reconcile** the prompt-2 sentinel shape with the runner's refusal
   classifier in the `_ocr_one_page` section: state explicitly that
   `(result.transcript == "" and result.is_illustration is False)`
   counts as a refusal-style attempt alongside
   `_looks_like_refusal(result.transcript)`. Apply both on the
   attempt-loop branch AND on the cache-hit branch. Promote Open
   Question #1 to a settled rule. (**C2, M6**)
2. **Justify** the `bool needs_review` choice over the existing
   `status: ReviewStatus` enum idiom: add one ADR sentence under
   "Consequences" explaining Prepare emits only a binary signal. If the
   user instead wants `ReviewStatus`, swap the contract diff
   accordingly and propagate to `text_units.py` construction and tests.
   (**C1**)
3. **Delete** `_ocr_attempt(...)` from the file-level change list and
   from the ADR; the worker calls the per-attempt `ocr_fn` directly.
   (**M1, architect rev. 1**)
4. **Replace** the `tuple[list[OcrPageResult], list[bool]]` return of
   `_ocr_all_pages` with `list[_OcrPageOutcome]` where
   `_OcrPageOutcome` is a runner-private
   `@dataclass(frozen=True)` carrying `(page, result, needs_review)`;
   extract the `needs_review` tuple at the single call site in
   `run_prepare`. (**M2, architect rev. 2**)
5. **Add** one ADR sentence justifying retry-in-runner over
   retry-in-`run_codex_ocr` (e.g. "policy stays co-located with
   sentinel-emission decision"). (**Architect rev. 3**)
6. **Add** one ADR sentence bounding the `schema_version` exemption:
   "any contract change after the first Transform-stage consumer lands
   MUST bump `schema_version` even if purely additive." (**Architect
   rev. 4**)
7. **Add** one bullet under "Open questions" flagging the prompt
   escalation as a hypothesis verified only by the manual recovery
   test; if `review_count == 5` after the recovery test, the
   escalation strings need re-tuning before declaring the slice
   shipped. (**Architect rev. 5**)
8. **Add** a direct contract-level test in
   `tests/automations/ln_voice_over_v2/stages/prepare/test_contracts.py`
   (or extend an existing file if discovered at implementation time)
   asserting (a) `PreparedTextUnit.model_validate_json(...)` succeeds
   when `needs_review` is omitted and defaults to `False`, and (b) a
   payload with an unknown key (e.g. `"needs_revue": true`) raises
   `pydantic.ValidationError`. Pin the test name(s) in the plan.
   (**M5, architect rev. 6**)
9. **Add** an "Atomic-commit ordering" subsection to the plan stating
   the contract diff, `build_text_units` signature change, runner
   unpack, and test updates must land in a single commit; no
   intermediate state may have an unaligned signature. (**M3**)
10. **Add** one sentence under the manual recovery test pinning the
    concurrency-fallback rule: "If the first attempt at `--workers 8`
    produces `review_count > 5`, re-run with `--workers 4` to rule out
    concurrency-induced rate-limiting before re-tuning prompts."
    (**M4**)
11. **Add** one sentence to "Contract change scope (limited)" stating
    explicitly that `docs/lnvo/contracts-index.md` does **not** need an
    update (artifact name unchanged, no new shared rule). (**m3**)
12. **Add** one sentence to the refusal-detection section noting that
    the regex matches straight ASCII apostrophe only; curly `'` would
    need a regex extension (out of scope). (**m5**)
13. **Pin** the `caplog` assertion shape in
    `test_runner_retry.py::cache_with_refusal_recomputes`: filter
    records by `levelname == "WARNING"` and substring match on the
    format string, then `len == 1`. Same pattern for `mixed_batch`'s
    INFO/WARNING expectations. (**A3 ambiguity disambiguator**)

13 atomic revisions. Items 1, 2 are the two CRITICAL items; items 3–10
are MAJOR; items 11–13 are MINOR/clarity.

---

ITERATE — Locked inputs and Pydantic semantics are honored, but two
CRITICAL design-collision findings (prompt-2 sentinel vs. refusal
classifier; bool field vs. `ReviewStatus` enum idiom) plus all 7
architect revisions remain unaddressed, requiring 13 atomic revisions
before APPROVE.

## Iteration 2 — re-evaluation of revised plan

verdict: APPROVE (conditional)
timestamp: 2026-05-26T02:00:00Z

13/13 round-1 critic revisions resolved with line-level evidence in the revised plan. Cross-checked the Architect's iteration-2 verdict: agree that R1 (matrix-cell at line 386, Expected/Reason contradiction) is the only blocking item. Agree R2-R4 are cosmetic/deferrable.

### Round-1 revisions status

All 13 resolved:
- C1 (sentinel collision → `_is_failed_ocr` covers both branches on attempt + cache paths): lines 15, 45, 72, 75, 201-204, 238, 243-245.
- C2 (`bool` justified vs ReviewStatus): lines 64-66, 77, 82, 154.
- C3 (delete `_ocr_attempt`): line 231; absent from imports (275) and worker body (234-246).
- C4 (`_OcrPageOutcome` replaces parallel lists): lines 215-223, 248-264, 266-272.
- C5 (ADR retry-in-runner rationale): line 76.
- C6 (`schema_version` exemption bounded): line 89.
- C7 (escalation as hypothesis): line 579.
- C8 (back-compat contract tests): lines 460-489.
- C9 (atomic-commit grouping): lines 156-158.
- C10 (concurrency fallback rule): line 557.
- C11 (contracts-index no-update justified): lines 152-154 + 82.
- C12 (apostrophe scope ASCII straight only): lines 195, 583.
- C13 (`caplog` filter shape pinned): lines 394-404, 422, 441-442, 444, 450.

### Regression hunt — clean

- No dangling `_ocr_attempt` references.
- No parallel-list / string-discriminator pattern remains.
- Sentinel cache-resume bug closed: line 238 + test at 449-453.
- `_is_failed_ocr` does NOT reject legit `(transcript="", is_illustration=True)`: matrix row + test at 454-458.
- `extra="forbid"` round-trip pinned: tests at 466-472, 483-489.
- `bool` choice justified in ADR (line 77, four-sentence rationale citing `dialogue/contracts.py:38` and `scenes/contracts.py:80`).
- Atomic-commit grouping satisfies CLAUDE.md Contract Changes protocol (lines 156-158).

### Locked-input verification

All 14 locked inputs realized at the cited lines. No iteration-1 revision contradicts any locked input.

### Newly-introduced issues beyond Architect R1

None blocking. Architect R1 is the only load-bearing inconsistency.

### Verdict

APPROVE conditional on R1 being applied; orchestrator may patch in-place.

Items still unresolved (excluding R1): 0.
