"""Light novel text-to-reviewed-attribution pipeline.

Converts a light novel Volume into reviewed, speaker-attributed chapter JSON by:
1. Splitting source material into chapters.
2. Cleaning text artifacts and parsing typed segments.
3. Attributing dialogue to speakers via LLM-assisted workflows.
4. Reviewing and validating the canonical attribution output.

Each stage is independently runnable. Intermediate results are stored as
inspectable JSON/text files under
~/.assistant/ln_voice_over/projects/<series>/<volume>/.
"""
