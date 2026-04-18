# Series/Volume Layout

Projects are organized as nested directories under `~/.assistant/ln_voice_over/projects/`: one folder per **series**, with one subfolder per **volume**. The character registry and voice assignments live at the series level so that all volumes of the same light novel share one cast.

```
~/.assistant/ln_voice_over/projects/
└── classroom-of-the-elite-year-2/          ← SERIES
    ├── config/
    │   ├── characters.json                  (shared cast)
    │   └── voices.json                      (shared voice assignments)
    ├── v6/                                  ← VOLUME
    │   └── source/ chapters/ cleaned/ parsed/ extracted/ resolved/ reviewed/ audio/ illustrations/
    ├── v7/
    │   └── ...
    └── v9/
        └── ...
```

Standalone books use the same shape with a single volume (e.g. `spice-and-wolf/v1/`).

## Why nested

Running the pipeline on multiple volumes of one light novel is the common case. Flat per-book folders would force us to either copy character and voice configs between volumes (they drift) or point at another project's configs (confusing, fragile). Nesting keeps the series together, models the real relationship, and lets a single edit to `config/voices.json` propagate to every volume.

## What lives where

| Scope   | What                                                                         |
|---------|------------------------------------------------------------------------------|
| Series  | `config/characters.json` — character registry (shared cast)                  |
| Series  | `config/voices.json` — voice mappings (per-character TTS voice)              |
| Volume  | `source/`, `chapters/`, `cleaned/`, `parsed/`, `extracted/`, `resolved/`, `reviewed/`, `illustrations/`, `audio/` |

### Config is series-level only

There is no per-volume config. If a voice needs to change, it changes for every volume (edit the series config). If a new volume introduces a new one-off character, add them to the series `characters.json` — the registry is allowed to grow. No volume-level overrides, no merge logic.

This is a deliberate design choice: voice continuity across volumes is the whole point of the series layout. A reader hearing the same light-novel protagonist switch voices between v6 and v7 would break immersion, so the data model prevents that from happening by accident.

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

## Migration from the flat layout

Older project trees were flat (`projects/classroom-of-the-elite-year-2-v7/` with configs inside). A one-time migration script moves them to the nested layout:

```bash
uv run python -m automations.ln_voice_over.scripts.migrate_to_series \
    --series classroom-of-the-elite-year-2 \
    --volume classroom-of-the-elite-year-2-v6:v6 \
    --volume classroom-of-the-elite-year-2-v7:v7 \
    --volume classroom-of-the-elite-year-2-v9:v9 \
    --promote-config-from classroom-of-the-elite-year-2-v7 \
    --dry-run
```

Drop `--dry-run` to execute. `--promote-config-from` picks which volume's `config/` becomes the new series-level config (the one with your assigned voices).

## Implementation pointers

- `automations/ln_voice_over/config.py` — `series_dir()`, `volume_dir()`, `SERIES_SUBDIRS`, `VOLUME_SUBDIRS`.
- `automations/ln_voice_over/project.py` — `resolve_volume()` (the one place that parses a CLI arg into a series/volume pair), `load_characters()`, `load_voices()`, `list_series()`, `list_volumes()`.
- `automations/ln_voice_over/init_project.py` — `create_project(series, volume)` creates both levels idempotently and seeds a placeholder series config if none exists.
