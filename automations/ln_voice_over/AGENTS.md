# LN Voice Over - Codex Rules

These rules apply to `automations/ln_voice_over/` and its tests under
`tests/automations/ln_voice_over/`.

## First Read

Before changing this sub-project, read:

1. `automations/ln_voice_over/README.md` for the pipeline shape.
2. `automations/ln_voice_over/CONTEXT.md` for the domain language.
3. Relevant ADRs under `automations/ln_voice_over/docs/adr/` before changing any
   behavior they cover.

Use the terms from `CONTEXT.md` in code, tests, and docs. Prefer **Volume** over
"book" except when referring to the concrete `source/book.json` artifact.
Use **Narrator** terminology in active code, docs, prompts, and schema work.

## Scope

- Treat this as an automation, not a public library surface. Keep changes local
  to `automations/ln_voice_over/` and matching tests unless the user explicitly
  asks for shared-library work.
- This sub-project is self-contained. Follow the root rule files, this file,
  and the files named in **First Read**; ignore conventions from sibling
  automations or unrelated repo docs.
- Do not modify `src/assistant/` as part of LN voice-over work without a separate
  plan.
- Keep generated project data under `~/.assistant/ln_voice_over/projects/` out of
  the repository unless the user explicitly asks to inspect or migrate it.
- Respect a dirty worktree. Do not revert user changes or untracked files.

## Pipeline Contracts

The implemented pipeline is:

```text
SOURCE -> SPLIT -> PARSE -> EXTRACT -> REVIEW
source/  chapters/ parsed/ extracted/ reviewed/
```

- Series data lives at `<series>/config/`; volume data lives at
  `<series>/<volume>/`.
- The character registry is series-level and shared across volumes.
- `reviewed/chapter_NN[_M].json` is canonical build output. Do not hand-edit it
  as a fix; fix upstream inputs, prompts, registry, or code and re-run.
- `reviewed/` data must obey the speaker grammar from `CONTEXT.md`:
  - `narration` and `chapter_header` segments use `"Narrator"`.
  - `dialogue` uses a registry-canonical character name or `"Unknown"`.
  - `scene_break` uses `null`.
- A registry gap may exist in intermediate files, but REVIEW must hard-fail
  before writing canonical reviewed data while any gap remains open.
- Voice mapping is accepted-only canonical data. AI-generated voice proposals are
  throwaway until a human promotes them into `voice_mapping.json`.

## Claude Skill Parity

The legacy Claude commands are operational specs:

- `.claude/commands/setup-book.md`
- `.claude/commands/attribute-speakers.md`
- `.claude/commands/review-attribution.md`

When porting or replacing them for Codex, preserve their file contracts and
human-in-the-loop boundaries. The Python scripts do deterministic file I/O and
bookkeeping; LLM steps should stay isolated to OCR, speaker attribution,
Narrator detection, and disagreement resolution.

For attribution/review prompt behavior, preserve these rules:

- Use speech tags after dialogue first, then before dialogue with care.
- `"I said/replied/asked"` means the chapter Narrator is speaking actual quoted
  dialogue.
- Embedded quoted words inside narration are `"Narrator"`.
- Long first-person exposition mis-tagged as `dialogue` is `"Narrator"`, not the
  Narrator character's canonical name.
- Unnamed staff, announcers, bystanders, or unresolved speakers are `"Unknown"`.

## Coding Rules

- Follow existing module boundaries: `project.py` resolves series/volume paths,
  `config.py` owns constants, `split.py` handles chapter boundaries, `parse.py`
  handles cleanup and segmentation, `models.py` owns Pydantic data shapes.
- Prefer structured parsing and Pydantic models over ad hoc string edits when
  changing JSON artifacts.
- Preserve backward-compatible CLI slug parsing:
  - `<series>/<volume>` is canonical.
  - `<series>-v<N>` remains supported.
  - `<series>` defaults to `v1`.
- Keep scripts runnable as `python -m automations.ln_voice_over.scripts.<name>`.
- Do not add speculative abstractions for future TTS or voice engines. Implement
  the next concrete pipeline step and document the contract.
- Use ASCII in new files unless existing source text requires otherwise.

## Tests And Checks

Use focused checks for this sub-project:

```bash
uv run pytest tests/automations/ln_voice_over
uv run ruff check automations/ln_voice_over tests/automations/ln_voice_over
uv run ruff format automations/ln_voice_over tests/automations/ln_voice_over
```

For broad changes that may affect packaging or the `lnvo` entry point, also run:

```bash
uv run pytest
```

Commits are allowed for completed, verified LN voice-over feature slices. Stage
only in-scope files; do not include unrelated dirty or untracked files from the
shared worktree.
