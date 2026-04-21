# Legacy

Code in this folder is **not part of the active pipeline** but is preserved for future use. It works today, just isn't the recommended path.

## `extraction.py`

Per-dialogue LLM speaker attribution (Ollama + OpenRouter), orchestrator for the `lnvo extract` CLI command. Accuracy with today's cheap/local models is well below the skill-based path (`/attribute-speakers`), so the skill is the default and this module is kept only so the CLI path still works and so the approach is available to resurrect when local/cheap models improve.

- Entry point: `lnvo extract` in `../cli.py` (imports from here).
- Primitives it relies on stay outside `legacy/`: `../llm.py` (Ollama / OpenRouter client) and `../config.py`'s `MODEL_REGISTRY`. Any future module can reuse those directly without touching this file.
