"""Stage 6: SYNTHESIZE + ASSEMBLE — TTS generation and audio concatenation.

Two sub-steps:
1. Synthesize: convert each text segment to audio via TTS provider,
   with content-addressable caching to avoid redundant API calls.
2. Assemble: concatenate segment audio files into chapter-level MP3s
   with appropriate silence between segments.

Caching uses sha256(voice_id:text) as the key — changing a speaker
attribution only re-synthesizes that one segment on re-run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .models import Chapter, CharacterRegistry, Segment, VoiceConfig, VoiceMapping
from .providers.base import TTSProvider


def cache_key(text: str, voice_id: str) -> str:
    """Generate a content-addressable cache key for a synthesized segment.

    Args:
        text: The text that was synthesized.
        voice_id: The voice used for synthesis.

    Returns:
        First 16 characters of the sha256 hex digest.
    """
    content = f"{voice_id}:{text}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def resolve_voice(
    segment: Segment,
    chapter: Chapter,
    voice_config: VoiceConfig,
    registry: CharacterRegistry,
) -> VoiceMapping | None:
    """Determine which voice to use for a segment.

    Resolution logic:
    - scene_break → None (silence, no TTS)
    - chapter_header → default_narrator
    - narration → pov_character's voice if set, else default_narrator
    - dialogue/inner_thought → speaker's mapped voice → gender default → narrator

    Args:
        segment: The segment to resolve a voice for.
        chapter: The chapter (for pov_character).
        voice_config: Voice mappings and defaults.
        registry: Character registry (for gender lookup on fallback).

    Returns:
        VoiceMapping to use, or None for silence (scene breaks).
    """
    ...


def synthesize_segment(
    text: str,
    voice_mapping: VoiceMapping,
    provider: TTSProvider,
    cache_dir: Path,
) -> Path:
    """Synthesize a single segment, using cache if available.

    Checks for existing cached audio before calling the TTS provider.
    Writes new audio to cache on synthesis.

    Args:
        text: Text to synthesize.
        voice_mapping: Voice to use.
        provider: TTS provider instance.
        cache_dir: Directory for cached segment audio files.

    Returns:
        Path to the audio file (cached or newly created).
    """
    ...


def compute_silence_ms(
    current_segment: Segment, next_segment: Segment | None
) -> int:
    """Determine silence duration to insert after a segment.

    Uses the SILENCE_DURATIONS_MS config based on the transition type
    (dialogue→dialogue, narration→dialogue, scene break, etc.).

    Args:
        current_segment: The segment just synthesized.
        next_segment: The following segment, or None if last.

    Returns:
        Silence duration in milliseconds.
    """
    ...


def assemble_chapter(
    segment_audio_paths: list[Path | None],
    segments: tuple[Segment, ...],
    output_path: Path,
) -> Path:
    """Concatenate segment audio files into a single chapter MP3.

    Inserts computed silence between segments. None entries in
    segment_audio_paths (from scene breaks) produce only silence.
    Uses pydub for concatenation.

    Args:
        segment_audio_paths: Ordered list of audio file paths (or None).
        segments: Chapter segments (for computing silence durations).
        output_path: Path to write the final chapter MP3.

    Returns:
        Path to the assembled chapter audio file.
    """
    ...


def synthesize_chapter(
    chapter: Chapter,
    voice_config: VoiceConfig,
    registry: CharacterRegistry,
    provider: TTSProvider,
    output_dir: Path,
    cache_dir: Path,
) -> Path:
    """Orchestrate full synthesis for one chapter.

    For each segment: resolve voice → synthesize (with cache) → collect.
    Then assemble all segment audio into the final chapter file.

    Args:
        chapter: Reviewed chapter with attributed segments.
        voice_config: Voice mappings and defaults.
        registry: Character registry for gender fallback.
        provider: TTS provider instance.
        output_dir: Directory for final chapter audio.
        cache_dir: Directory for cached segment audio.

    Returns:
        Path to the final chapter MP3 file.
    """
    ...
