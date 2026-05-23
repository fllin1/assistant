# LN Voice Over

A pipeline that turns a light novel volume into per-chapter JSON of typed, speaker-attributed segments — eventually feeding a TTS layer where each character has a distinct voice.

## Language

**Volume**:
A single book in a series — the unit at which the pipeline runs end-to-end.
_Avoid_: book (overloaded — "book.json" is the source artifact, not the volume)

**Series**:
A set of related volumes that share a character cast.
_Avoid_: franchise

**Chapter**:
A top-level division of a volume, identified by a chapter number.

**Sub-chapter**:
A division *inside* a chapter where the **Narrator** changes. Signaled by the publisher with bare `N.M` marker lines (e.g. `7.1`, `7.2`). The publisher uses these markers iff the Narrator shifts — a Narrator change without an `N.M` marker is not expected, and `N.M` markers do not appear for any other reason. Detection requires ≥ 2 such markers in the same chapter with strictly-increasing minors and major matching the chapter number; this guards against incidental single markers (footnotes, problem numbers like `2.1`).
_Avoid_: section, scene (a scene break is a different concept — see **Scene break**)

**Segment**:
The atomic unit produced by PARSE. One of four **Segment types**: `narration`, `dialogue`, `scene_break`, `chapter_header`. Each segment carries a **Speaker** in canonical (`reviewed/`) data, with one carve-out for `scene_break` (see **Speaker grammar**).

**Speaker grammar** (in `reviewed/`):
- `narration` → `"Narrator"`
- `dialogue` → canonical character name **or** `"Unknown"`
- `chapter_header` → `"Narrator"` (the chapter title is read by whoever fills the **Narrator** role for that chapter)
- `scene_break` → `null` (the only legal null in `reviewed/`; scene breaks are structural, not spoken — synthesis renders them as silence / sting / fade)

Empirically, `scene_break` does not occur in the current source material (Classroom of the Elite). The grammar accommodates it for general light-novel support; if it never appears it costs nothing.

**Front matter**:
Volume content before the first chapter heading (preface, prologue, dedication, illustrations descriptions). When present, SPLIT emits it as a Chapter (`chapter_00`) and it follows the same rules as any other Chapter — Narrator detection, attribution, registry validation, the lot. No special case.

**Reviewed artifact**:
The canonical `reviewed/chapter_NN[_M].json`. **Immutable build output** — to fix one, fix upstream (registry, prompts, parsed/) and re-run, never hand-edit. The file is what downstream synthesis reads; it must be reproducible from (Volume source + Character registry + LLM behaviour).

**Speaker**:
The label on a **Segment**. In canonical (`reviewed/`) data, exactly one of: a canonical name from the **Character registry**, the literal `"Narrator"`, or the literal `"Unknown"`. `null` is only valid mid-pipeline (post-PARSE, pre-EXTRACT) and never appears in `reviewed/`.

**Unknown speaker**:
The terminal label `"Unknown"` for a **Segment** the attribution + judge passes could not confidently attribute. Maps to a dedicated "unknown" voice at synthesis time. Distinct from `null` (which means "not yet attributed").

**Narrator**:
The role of "whose voice narrates this **Chapter** / **Sub-chapter**." Exactly one Narrator role per unit. The role is filled either by a known **Character** (first-person chapter — that character's interiority *is* the narration) or by the **Omniscient narrator** (third-person chapter — no specific character backs the role). Narration **Segments** are labeled with the **Speaker** token `"Narrator"` regardless of which fills the role; voice resolution dispatches on the chapter's narrator field at synthesis time.
_Avoid_: POV character, POV, point-of-view character (historical names — see Flagged ambiguities)

**Omniscient narrator**:
The default, character-less Narrator used for third-person chapters. Has its own dedicated voice (the registry's `narrator_name` slot). Represented in data by `narrator_status = "detected"` together with a null `narrator` field on the **Chapter** — null alone is not "omniscient"; the status field qualifies it (see **Narrator status**).

**Narrator status**:
A two-state enum on each **Chapter** capturing whether Narrator detection has run:
- `"unset"` — SPLIT has produced the unit; Narrator detection has not run. The narrator field is null and uninformative.
- `"detected"` — Narrator detection has run. The narrator field is now authoritative: a canonical character name = first-person Narrator, null = **Omniscient narrator**.

The status separates "we don't know" from "we know it's omniscient" so that re-running detection skips already-detected units idempotently.

**Scene break**:
A structural break within a chapter (`***`, `---`, `* * *`, …). Distinct from a **Sub-chapter**: scene breaks do not change the **Narrator**.

**Character registry**:
The series-level source of truth for character canonical names, aliases, gender, and role. Lives at `<series>/config/characters.json` and is shared across all volumes in the series. Every canonical character name appearing anywhere in canonical data — **Speaker** values in `reviewed/` segments and the `narrator` field on a **Chapter** — must resolve to a registry entry. Voice assignment for **Characters** lives outside this pipeline (see **Voice-tuning project**).

**Voice-tuning project**:
External companion repo at `~/_workspace/tools/voice-tuning/` — a local web app that auditions TTS voices (Kokoro, Hume, Orpheus stub) for CoTE-specific character slots. Used as a *testing harness*, not a source of truth: only Ayanokouji's voice is currently locked there. Voice selection for ln_voice_over flows the other way — proposals (AI- or human-originated) are tried in voice-tuning, then promoted into ln_voice_over's authoritative artifact (see **Voice mapping**).

**Voice mapping**:
The series-level artifact `<series>/config/voice_mapping.json` — the **single source of truth** synthesis reads to resolve a **Speaker** to a voice. **Accepted-only**: every entry has been heard and confirmed; there is no "proposed" status inside this file. Keyed by canonical character name (matching the **Character registry**), plus two reserved keys `"Narrator"` (the **Omniscient narrator**'s default voice) and `"Unknown"`. Each entry carries the same fields voice-tuning's cast export uses (`engine`, `voice_id`, `speed`, `params`, `playback_speed`) so promotion from a tested cast is field-by-field copy. Synthesis is a pure function of `reviewed/<chapter>.json` + `voice_mapping.json`.

**Voice proposals**:
A separate, AI-generated artifact (e.g. `<series>/config/voice_proposals.json` or chat output). Lists candidate voices per character with a brief rationale, in a shape that can be fed into voice-tuning's batch-generate flow. Never read by synthesis. Workflow: AI proposes → human auditions in voice-tuning → human (optionally) promotes a chosen voice into `voice_mapping.json`. Proposals are throwaway; the mapping is canonical. **Voice proposals never include a `speed` field other than `1.0`** — pacing is shaped via voice choice and engine-side params (Orpheus temperature, Hume description text), never via speed manipulation.

**Synthesis output**:
The downstream of REVIEW. For each `reviewed/chapter_NN[_M].json`, synthesis produces:
1. Per-segment WAV stems under `<volume>/audio/chapter_NN[_M]/segment_<index>.wav`. Each stem is content-addressed (cache key from engine, voice_id, params, text), so re-runs after a Speaker edit re-render only the affected segments.
2. A concatenated per-chapter WAV at `<volume>/audio/chapter_NN[_M].wav`, produced from the stems by an audio-policy step (pause/silence between segments, chapter-header treatment, scene-break rendering when present).

WAV throughout — no MP3 in the pipeline. Stems are not deleted after concat; they are the cache.

**Audio policy — gap rule**: type-aware. Concat inserts silence between consecutive segments based on the segment-type transition (e.g. `chapter_header → narration`: long beat; `narration → dialogue`: medium; `dialogue → dialogue`: short; `dialogue → narration`: medium). Per-character pause overrides are deferred — the type-aware baseline ships first; if specific characters need bespoke pacing, that's added on top once the baseline is audible. Concrete millisecond values to be tuned by ear; the structure is config-driven (a small policy table at the volume or series level).

**Audio policy — quote rule**: the per-segment renderer strips a leading/trailing pair of quote characters from `dialogue` segments before passing text to the engine. Other segment types (`narration`, `chapter_header`) are passed verbatim — embedded quoted words in narration (e.g. `She muttered "trap" under her breath.`) are content, not delimiters. The rule is uniform across all three engines (Kokoro, Orpheus, Hume), which keeps engine-mix artifacts consistent.

**Synthesis preflight**: before rendering any segment of a chapter, synthesis collects the distinct **Speaker** values from the chapter's segments and validates that each has an entry in `voice_mapping.json`. If any are missing, synthesis lists them all, exits non-zero, and renders nothing. Mirrors the REVIEW boundary's hard-validation pattern — fail fast before expensive work (Hume calls cost API credits; partial-run waste is avoided).

**Synthesis runtime — retry policy**: per-segment engine calls follow a retry-then-fail rule. Up to 3 attempts with exponential backoff (e.g. 1s / 4s / 16s) on the same engine + voice. If all retries fail, synthesis halts, leaves the content-addressed stems already on disk, and exits non-zero. The user resolves the underlying issue (wait out the outage, top up credits, restart the model) and re-runs — the cache reuses every successful stem; only the failed segment(s) re-attempt. No engine-fallback (Hume → Kokoro) ever happens automatically: it would cause silent quality regressions and is rejected as a policy.

**Synthesis cost guardrail**: after preflight (voice-mapping validation) and before any rendering, synthesis prints a plan summary — segment count per engine, estimated Hume cost in API credits, total — and prompts to continue (Y/N). The "no" path is the de-facto dry-run: the user sees the plan and exits with no calls made. A separate `--dry-run` flag is unnecessary because the prompt already exposes the plan.

**Synthesis re-run semantics**: the default is implicit incremental — re-running `lnvo synthesize` after any change (`voice_mapping.json` edit, prompt fix, registry update) re-renders only segments whose cache key changed; cached stems are reused. Concat always re-runs (cheap, ms) so the chapter WAV reflects current stems. A `--rebuild` flag (scoped to chapter or volume) forces full re-render bypassing the cache — escape hatch for model upgrades, cache corruption, or verifying nothing is stale. The user never has to specify "what changed"; the cache key encodes that.

**Registry gap**:
A name produced by the LLM (during **Narrator detection** or **Speaker** attribution) that the registry's match chain (exact → alias → honorific-strip → component → fuzzy) cannot resolve to an existing **Character**. Gaps are not silently dropped; they are surfaced and closed via the **Registry-population workflow**.

**Registry-population workflow**:
The process that closes a **Registry gap**. Mixed model + human: the model proposes a resolution (existing character + new alias, or new character with proposed canonical name and metadata), the human confirms or corrects, the registry is updated, and the originating attribution / narrator field is rewritten with the canonical name. The registry is never auto-edited without confirmation.

Gaps are handled **accumulate-then-batch**, not pause-on-encounter. The rule applies uniformly to both **Narrator detection** and **Speaker** attribution: each writes the LLM-raw name as a placeholder into its intermediate output (the manifest's `narrator` field for detection; per-chunk attribution JSONs for **Speaker**) and logs the gap. A dedicated resolution step processes the accumulated gap log before canonical data is written. The "every canonical name is registry-canonical" contract holds at the boundary into `reviewed/`, not at every intermediate file.

## Relationships

- A **Series** contains one or more **Volumes**
- A **Volume** is split into **Chapters**; a **Chapter** may further split into **Sub-chapters**
- Every **Chapter** or **Sub-chapter** has exactly one **Narrator** role; the role is filled either by a **Character** or by the **Omniscient narrator**
- A **Chapter** / **Sub-chapter** contains an ordered sequence of **Segments**
- Every **Segment** has exactly one **Speaker** (in canonical `reviewed/` data)
- The **Speaker** `"Narrator"` resolves, for that chapter, to the voice of whoever fills the **Narrator** role (a **Character**'s voice, or the **Omniscient narrator**'s default voice)
- Every canonical character name (in **Speaker** values or in a **Chapter**'s `narrator` field) is a **Character** in the **Character registry**
- A **Registry gap** is closed by the **Registry-population workflow** before canonical data is written
- The boundary into `reviewed/` is **hard-validated**: REVIEW refuses to write canonical data while any **Registry gap** is open for the **Chapter** / **Sub-chapter**

## Example dialogue

> **Dev:** "Chapter 7 has four sub-chapters — does each one get its own **Narrator**?"
> **Author:** "Yes. The publisher splits 7 into `7.1`/`7.2`/`7.3`/`7.4` precisely *because* the **Narrator** changes. Each sub-chapter is one **Narrator** start to finish."
> **Dev:** "And inside `7.1`, when Ayanokoji thinks something, that's a `narration` **Segment** with **Speaker** `\"Narrator\"`?"
> **Author:** "Right. If he says it out loud — quoted dialogue — that's a `dialogue` **Segment** with **Speaker** `\"Ayanokoji Kiyotaka\"`. Same voice at synthesis time, different label."

## Flagged ambiguities

- **POV character** vs **Narrator** — resolved: there is only one concept, **Narrator**. The codebase still uses `pov_character` in places (`Chapter.pov_character`, manifest field, `save_pov` script, `/attribute-speakers` "auto-detects POV"). Rename pending.
- **Speaker** `"Narrator"` vs the **Narrator**'s canonical name — resolved: `"Narrator"` is a structural token on segments, the canonical name lives once on the chapter. They map to the same TTS voice but are kept distinct in the data.
- **book** — resolved: in this context, "book" appears only as the artifact name `book.json` (the SOURCE output). The pipeline unit is a **Volume**, not a "book."
- **Sub-chapter trigger as heuristic vs. definition** — resolved: the `N.M` marker is treated as **definitional**, not heuristic. Empirical spot-check on `classroom-of-the-elite-year-2/v4` showed the trigger never produced a wrong split and chapters without splits had no internal Narrator drift. If a future volume disproves this, the resolution is to revisit the rule, not to silently work around it.
- **`pov_character: null` in current manifests** — resolved: today's null overloads "not yet detected" and "omniscient." After the rename, the **Chapter** carries both `narrator_status` and `narrator`; only `narrator_status = "detected"` + `narrator = null` means **Omniscient narrator**. Existing manifests need migration: rows where detection ran but returned null become `status="detected"`, rows where detection never ran become `status="unset"`.
- **`chapter_header` segments wrapped in literal quote marks** — open: empirically the `text` field of `chapter_header` segments contains a leading and trailing `"` (e.g. `'"Chapter 1: Amasawa Ichika\'s Soliloquy"'`). This is a PARSE artifact, not a contract; chapter headings aren't dialogue and shouldn't be quoted. Fix in PARSE; downstream synthesis should not have to strip quotes from headers.
- **Quote marks in `dialogue.text`** — open: dialogue `text` includes the surrounding quote characters. Whether synthesis strips them, leaves them, or treats them as a voice cue is a downstream policy decision (deferred to the synthesis design).
- **Kushida public/private as two Characters** — resolved (option B): a character with multiple voice-relevant modes is represented as multiple **Characters** in the registry, each with a distinct canonical name and a distinct **Voice mapping** entry. Attribution decides the mode at attribution time using a context rule grounded in cross-volume source analysis (see **Mode-disambiguation rule** below). The "two canonical names refer to the same underlying person" relationship is implicit for now; if cross-volume character bookkeeping ever needs it, an explicit alias mechanism can be added.

  **Mode-disambiguation rule (Kushida Kikyou):**
  - Default: public (`"Kushida Kikyou"`).
  - Promote to private (`"Kushida Kikyou (private)"`) when **two of three** signals fire: (1) audience consists only of characters who already know her secret (Ayanokouji, Horikita, post-exam Ibuki, Amasawa, Yagami, Haruka, and similar); (2) content is threatening, contemptuous, or admits manipulation (terseness alone is insufficient); (3) narrator framing names the shift ("true colors", "out of public eye", "no longer reserved", "wry smile", "cold eyes", "the mask").
  - Override-back-to-public: explicit re-entry of unaware audience or narrator phrases like "angel mode" / "with people around" flip subsequent segments back to public, even when residual edge-y content remains.
  - Uncertainty (signals split, one fires weakly): emit `"Kushida Kikyou (uncertain)"` — a **Registry gap by construction** that routes to the **Registry-population workflow** for human resolution before `reviewed/`.
  - Granularity: per-segment. Shifts can occur between adjacent segments when audience composition changes mid-scene.

  Empirical basis: cross-volume agent analysis of v4/v6/v7/v9/v10. Narrator framing is reliable when present but absent in v6 Ch6 — the audience+content combination must carry the rule when narrator stays silent. Mid-scene shifts confirmed in v6 Ch6 and v7 Ch7. False positives across the corpus were rare; the main failure mode would be missing a private segment that lacks both narrator framing and an explicit audience cue.
