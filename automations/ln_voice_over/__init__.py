"""Light novel text-to-audiobook pipeline with per-character voice synthesis.

Converts raw light novel text files into multi-voice audiobooks by:
1. Splitting volumes into chapters
2. Cleaning text artifacts (watermarks, page numbers)
3. Parsing text into typed segments (narration, dialogue, thoughts)
4. Attributing dialogue to characters via LLM
5. Manual review of attributions
6. TTS synthesis with per-character voices and audio assembly

Each stage is independently runnable. Intermediate results are stored as
inspectable JSON/text files under ~/.assistant/ln_voice_over/projects/<book-slug>/.
"""
