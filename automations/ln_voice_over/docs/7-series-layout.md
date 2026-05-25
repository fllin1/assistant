# Series/Volume Layout

Projects are organized as nested directories under `~/.assistant/ln_voice_over/projects/`: one folder per **series**, with one subfolder per **volume**. The character registry lives at the series level so that all volumes of the same light novel share one cast.

For the full code and data-flow map around this layout, see
[architecture.md](architecture.md).

```
~/.assistant/ln_voice_over/projects/
└── classroom-of-the-elite-year-2/          ← SERIES
    ├── config/
    │   └── characters.json                  (shared cast)
    ├── v6/                                  ← VOLUME
    │   └── source/ chapters/ parsed/ extracted/ reviewed/ illustrations/
    ├── v7/
    │   └── ...
    └── v9/
        └── ...
```

Standalone books use the same shape with a single volume (e.g. `spice-and-wolf/v1/`).

## Why nested

Running the pipeline on multiple volumes of one light novel is the common case. Flat per-book folders would force us to either copy the character registry between volumes (they drift) or point at another project's config (confusing, fragile). Nesting keeps the series together, models the real relationship, and lets a single edit to `config/characters.json` propagate to every volume.

## What lives where

| Scope   | What                                                                                  |
|---------|---------------------------------------------------------------------------------------|
| Series  | `config/characters.json` — character registry (shared cast)                           |
| Volume  | `source/`, `chapters/`, `parsed/`, `extracted/`, `reviewed/`, `illustrations/`        |

### Config is series-level only

There is no per-volume config. If a new volume introduces a new character, add them to the series `characters.json` — the registry is allowed to grow. No volume-level overrides, no merge logic.

## Naming conventions

- **Series slug**: lowercase, hyphenated. Matches the book's canonical series title.
  - `classroom-of-the-elite-year-2` (not `cote-y2`)
  - `mushoku-tensei`
- **Volume slug**: short identifier, typically `v<N>`. No prefix — just the volume itself.
  - `v1`, `v7`, `v12`
  - `v4a` / `v4b` works for split volumes if a series uses those.

## Referencing projects from the CLI

All CLI commands accept the following forms:

| Form                                       | Meaning                                                      |
|--------------------------------------------|--------------------------------------------------------------|
| `<series>/<volume>`                        | Canonical. Always preferred.                                 |
| `<series>-v<N>`                            | Legacy flat slug. Auto-split into `(series, v<N>)`.          |
| `<series>`                                 | Series only. Volume defaults to `v1`.                        |

Examples:

```bash
lnvo split classroom-of-the-elite-year-2/v7        # canonical
lnvo split classroom-of-the-elite-year-2-v7        # legacy, still works
lnvo split spice-and-wolf                          # single-volume book → v1
```

The legacy form is kept as a compatibility shim for muscle memory. New projects should use the canonical form.

## Historical migration from the flat layout

Older project trees were flat (`projects/classroom-of-the-elite-year-2-v7/` with configs inside). They were migrated with a one-off local script that is not part of the current repository. If another flat tree needs migration, use the implementation pointers below: create the target series with `create_project(series, volume)`, promote one curated `config/characters.json` to the series `config/`, and move each volume's pipeline directories under its new volume folder.

## Implementation pointers

- `automations/ln_voice_over/config.py` — `series_dir()`, `volume_dir()`, `SERIES_SUBDIRS`, `VOLUME_SUBDIRS`.
- `automations/ln_voice_over/project.py` — `resolve_volume()` (the one place that parses a CLI arg into a series/volume pair), `load_characters()`, `list_series()`, `list_volumes()`.
- `automations/ln_voice_over/init_project.py` — `create_project(series, volume)` creates both levels idempotently and seeds a placeholder series config if none exists.
