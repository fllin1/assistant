"""Stage 8: Synthesize audio from reviewed chapters.

Reads a reviewed Chapter + series VoiceConfig + CharacterRegistry, runs
each segment through its assigned TTS provider, and concatenates the
per-segment WAVs with scene-appropriate silence into a single chapter WAV.

The pipeline is WAV-native from providers through to final export — no
intermediate MP3 re-encodes. Providers that only serve MP3 (Edge) decode
to WAV inside the provider itself, so the cache and assembly stages
always see lossless PCM.

Segments are cached on disk under `audio/segments/<cache_key>.wav`. The
cache key is `sha256(provider:voice_id:text:settings)[:16]`, so fixing a
single attribution and re-running only re-synthesizes the one changed
segment.

Public surface:
    resolve_voice(segment, chapter, voices, registry) -> VoiceMapping | None
    synthesize_segment(segment, mapping, cache_dir) -> Path
    assemble_chapter(chapter, voices, registry, audio_dir, ...) -> Path

The CLI wrapper lives in cli.py as `lnvo synthesize`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
from pydub import AudioSegment

from .models import (
    Chapter,
    CharacterRegistry,
    Segment,
    SegmentType,
    VoiceConfig,
    VoiceMapping,
)
from .providers.base import TTSSynthesisError
from .providers.registry import get_provider

logger = logging.getLogger(__name__)

# Target loudness per ITU-R BS.1770 (Apple Podcasts spec). Applied per
# segment so voice switches feel uniform instead of the Edge-is-quieter
# jumps you get with whole-track dBFS normalization.
_TARGET_LUFS = -16.0

# Segments shorter than this can't be reliably measured by pyloudnorm —
# the K-weighted gating block is 400ms; we want some headroom for a
# stable integrated loudness read. Below the threshold we peak-normalize
# via dBFS instead.
_MIN_DURATION_FOR_LUFS_MS = 1000
_DBFS_FALLBACK_TARGET = -20.0

# Kokoro's pipeline is a shared singleton and torch inference on one
# model contends on itself under multi-threading (cache thrash + non-
# re-entrant state). Serialize just the Kokoro calls while letting Edge
# and OpenAI keep the full thread pool.
_KOKORO_LOCK = threading.Semaphore(1)

# Gap table: (prev_type, curr_type) -> milliseconds. Any pair not listed
# falls back to 300ms (the narration<->narration default).
_GAP_MS: dict[tuple[SegmentType | None, SegmentType], int] = {
    (SegmentType.DIALOGUE, SegmentType.DIALOGUE): 150,
    (SegmentType.NARRATION, SegmentType.DIALOGUE): 300,
    (SegmentType.DIALOGUE, SegmentType.NARRATION): 300,
}

_SCENE_BREAK_MS = 600
_CHAPTER_HEADER_LEAD_MS = 1100

# Per-segment-type speed multipliers. TTS providers default to a somewhat
# slow pace; dialogues benefit from a little extra pep vs steady narration.
# Individual VoiceMapping.settings (if present) override these, and the
# CLI can pass a different policy via assemble_chapter(speed_policy=...).
DEFAULT_SPEED_POLICY: dict[SegmentType, float] = {
    SegmentType.NARRATION: 1.15,
    SegmentType.DIALOGUE: 1.20,
    SegmentType.CHAPTER_HEADER: 1.15,
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def resolve_voice(
    segment: Segment,
    chapter: Chapter,
    voices: VoiceConfig,
    registry: CharacterRegistry,
) -> VoiceMapping | None:
    """Pick the voice for a segment, or None for scene breaks (pure silence).

    Rules:
      * scene_break    -> None
      * chapter_header -> default narrator
      * narration      -> POV character's voice if chapter.pov_character is
                          set, else default narrator
      * dialogue       -> speaker's mapped voice, falling back to gender
                          default then narrator. No speaker => narrator.
    """
    match segment.segment_type:
        case SegmentType.SCENE_BREAK:
            return None
        case SegmentType.CHAPTER_HEADER:
            return voices.host if voices.host else voices.default_narrator
        case SegmentType.NARRATION:
            pov = chapter.pov_character
            if pov:
                char = registry.find(pov)
                gender = char.gender if char else "unknown"
                return voices.get_voice(pov, gender)
            return voices.default_narrator
        case SegmentType.DIALOGUE:
            if not segment.speaker:
                return voices.default_narrator
            char = registry.find(segment.speaker)
            gender = char.gender if char else "unknown"
            return voices.get_voice(segment.speaker, gender)


def cache_key(mapping: VoiceMapping, text: str, settings: dict | None = None) -> str:
    """Content-addressed segment ID. Includes provider so the same voice_id
    on two providers (hypothetical but possible) doesn't collide. Includes
    settings so a speed/pitch change invalidates the cache correctly."""
    parts = [mapping.provider, mapping.voice_id, text]
    if settings:
        parts.append(json.dumps(dict(sorted(settings.items())), separators=(",", ":")))
    payload = ":".join(parts).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _speed_for(
    segment_type: SegmentType,
    policy: dict[SegmentType, float] | None = None,
) -> float:
    """Per-segment-type speed multiplier (1.0 = provider default)."""
    return (policy or DEFAULT_SPEED_POLICY).get(segment_type, 1.0)


def _speed_settings(provider: str, speed: float) -> dict:
    """Translate a scalar speed multiplier into the provider's native key.

    Edge uses a percentage-string `rate`; OpenAI and Kokoro use a float
    `speed`. Returns an empty dict for speed == 1.0 so we don't introduce
    gratuitous settings that would bust the cache.
    """
    if speed == 1.0:
        return {}
    if provider == "edge":
        pct = round((speed - 1.0) * 100)
        return {"rate": f"{pct:+d}%"}
    return {"speed": speed}


def compute_settings(
    mapping: VoiceMapping,
    segment_type: SegmentType,
    speed_policy: dict[SegmentType, float] | None = None,
) -> dict:
    """Merge the speed policy with the mapping's explicit settings.

    Per-mapping settings win on key collision — the voice config is the
    user's authoritative override for a character with a distinctive pace.
    """
    speed = _speed_for(segment_type, speed_policy)
    policy = _speed_settings(mapping.provider, speed)
    return {**policy, **(mapping.settings or {})}


def strip_dialogue_quotes(text: str) -> str:
    """Drop surrounding curly or straight quotes. Edge TTS reads them aloud
    as "quote"; stripping them is cleaner. Only strips a matched pair at
    the boundaries — unbalanced or interior quotes are left alone."""
    openers = ("\u201c", '"')
    closers = ("\u201d", '"')
    if len(text) >= 2 and text.startswith(openers) and text.endswith(closers):
        return text[1:-1]
    return text


def gap_ms(prev: SegmentType | None, curr: SegmentType) -> int:
    """Silence (ms) to insert before `curr` given the previous segment type.

    First segment of a chapter (prev=None) => 0, no leading silence.
    Chapter headers always get a long lead regardless of what came before.
    Scene breaks produce their own silence (handled in assembly), so any
    neighbour pair involving SCENE_BREAK here returns 0.
    """
    if prev is None:
        return 0
    if curr == SegmentType.CHAPTER_HEADER:
        return _CHAPTER_HEADER_LEAD_MS
    if curr == SegmentType.SCENE_BREAK or prev == SegmentType.SCENE_BREAK:
        return 0
    return _GAP_MS.get((prev, curr), 300)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------


def _ensure_ffmpeg() -> None:
    """Abort early if ffmpeg isn't on PATH — pydub's own error is cryptic.

    Even though the pipeline is WAV-native, the Edge provider still needs
    ffmpeg to decode its MP3 stream to WAV once per new segment.
    """
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError(
            "ffmpeg is required by pydub (Edge provider decodes MP3 -> WAV) "
            "but was not found on PATH. Install it first "
            "(macOS: brew install ffmpeg)."
        )


def _audio_to_float_samples(audio: AudioSegment) -> np.ndarray:
    """Convert an AudioSegment to a float32 array in [-1, 1].

    Returns shape `(n_samples,)` for mono, `(n_samples, channels)` for
    multi-channel — the format pyloudnorm's Meter expects.
    """
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    max_int = float(1 << (8 * audio.sample_width - 1))
    samples /= max_int
    if audio.channels > 1:
        samples = samples.reshape((-1, audio.channels))
    return samples


def _normalize_to_lufs(audio: AudioSegment, target_lufs: float = _TARGET_LUFS) -> AudioSegment:
    """Return `audio` gain-adjusted to `target_lufs` integrated loudness.

    Segments below `_MIN_DURATION_FOR_LUFS_MS` fall back to peak-based
    dBFS normalization — pyloudnorm's measurement is unstable on clips
    shorter than a couple of gating blocks (400ms each).
    """
    if len(audio) < _MIN_DURATION_FOR_LUFS_MS:
        if audio.dBFS == float("-inf"):
            return audio
        return audio.apply_gain(_DBFS_FALLBACK_TARGET - audio.dBFS)

    samples = _audio_to_float_samples(audio)
    meter = pyln.Meter(audio.frame_rate)
    current = meter.integrated_loudness(samples)
    if current == float("-inf") or np.isnan(current):
        return audio  # digital silence or measurement failure — leave alone
    return audio.apply_gain(target_lufs - current)


def _load_segment_audio(path: Path) -> AudioSegment:
    return AudioSegment.from_wav(path)


# ---------------------------------------------------------------------------
# Synthesis (per-segment) with retry + cache
# ---------------------------------------------------------------------------


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write `data` to `path` atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    tmp_path.rename(path)


def _invoke_provider(mapping: VoiceMapping, text: str, settings: dict) -> bytes:
    """Call the provider's synthesize, serializing Kokoro with the semaphore."""
    provider = get_provider(mapping.provider)
    if mapping.provider == "kokoro":
        with _KOKORO_LOCK:
            return provider.synthesize(text, mapping.voice_id, **settings)
    return provider.synthesize(text, mapping.voice_id, **settings)


def synthesize_segment(
    segment: Segment,
    mapping: VoiceMapping,
    cache_dir: Path,
    settings: dict | None = None,
    max_retries: int = 3,
) -> Path:
    """Return the cached WAV path for a segment. Synthesize on miss.

    Retries TTSSynthesisError with exponential backoff (1s, 2s, 4s) before
    giving up — handles transient rate limits / network blips without a
    dedicated retry dependency.
    """
    text = segment.text
    if segment.segment_type == SegmentType.DIALOGUE:
        text = strip_dialogue_quotes(text)

    effective_settings = settings or {}
    key = cache_key(mapping, text, effective_settings)
    out = cache_dir / f"{key}.wav"
    if out.exists():
        return out

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            audio = _invoke_provider(mapping, text, effective_settings)
            _atomic_write_bytes(out, audio)
            return out
        except TTSSynthesisError as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = 2**attempt
                logger.warning(
                    "TTS error (attempt %d/%d) for %s/%s: %s. Retrying in %ds.",
                    attempt + 1,
                    max_retries,
                    mapping.provider,
                    mapping.voice_id,
                    e,
                    delay,
                )
                time.sleep(delay)
    assert last_err is not None
    raise last_err


# ---------------------------------------------------------------------------
# Chapter assembly
# ---------------------------------------------------------------------------


def assemble_chapter(
    chapter: Chapter,
    voices: VoiceConfig,
    registry: CharacterRegistry,
    audio_dir: Path,
    parallel: int = 4,
    normalize: bool = True,
    speed_policy: dict[SegmentType, float] | None = None,
    verbose: bool = False,
) -> Path:
    """Synthesize every segment then concatenate into one chapter WAV.

    Args:
        chapter: Reviewed chapter with resolved speakers.
        voices: Series-level voice mappings.
        registry: Series-level character registry (for gender lookup).
        audio_dir: Volume's `audio/` directory. Writes into `segments/`
            and `chapters/` subdirs.
        parallel: Max concurrent TTS calls across all providers. Kokoro
            calls serialize on an internal semaphore regardless — so
            mixed-provider chapters keep parallelism for Edge/OpenAI
            while Kokoro runs single-threaded.
        normalize: When True, apply per-segment LUFS normalization (target
            `_TARGET_LUFS`, -16). Falls back to dBFS peak normalization
            for segments shorter than 1s where LUFS is unreliable.
        speed_policy: Per-segment-type speed multipliers. Omit to use
            `DEFAULT_SPEED_POLICY`. Per-mapping settings still win on
            key collision.
        verbose: Print per-segment diagnostic (provider, voice, speed,
            cache status) to stdout during assembly.

    Returns:
        Path to the assembled `chapters/chapter_NN.wav`.

    Raises:
        FileNotFoundError: If ffmpeg is missing from PATH.
        TTSSynthesisError: If synthesis fails after all retries on any
            segment.
    """
    _ensure_ffmpeg()

    segments_dir = audio_dir / "segments"
    chapters_dir = audio_dir / "chapters"
    segments_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: resolve voice for each segment.
    plan: list[tuple[Segment, VoiceMapping | None]] = [
        (seg, resolve_voice(seg, chapter, voices, registry)) for seg in chapter.segments
    ]

    # Step 2: dedupe by cache_key (same line by same voice+settings = one
    # TTS call). Segments with None mapping (scene breaks) produce silence
    # at assembly time, not via TTS.
    work: dict[str, tuple[Segment, VoiceMapping, dict]] = {}
    for seg, mapping in plan:
        if mapping is None:
            continue
        text = (
            strip_dialogue_quotes(seg.text)
            if seg.segment_type == SegmentType.DIALOGUE
            else seg.text
        )
        settings = compute_settings(mapping, seg.segment_type, speed_policy)
        key = cache_key(mapping, text, settings)
        work.setdefault(key, (seg, mapping, settings))

    # Cache hits decided up-front so the report is accurate and we don't
    # even submit work for segments that already have WAVs.
    pending: list[tuple[str, Segment, VoiceMapping, dict]] = []
    cached_hits = 0
    for key, (seg, mapping, settings) in work.items():
        if (segments_dir / f"{key}.wav").exists():
            cached_hits += 1
        else:
            pending.append((key, seg, mapping, settings))

    synthesized = 0
    if pending:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = [
                pool.submit(synthesize_segment, seg, mapping, segments_dir, settings)
                for _, seg, mapping, settings in pending
            ]
            for future in futures:
                future.result()  # re-raises TTSSynthesisError if retries exhausted
                synthesized += 1

    # Step 3: concatenate in order. Normalize each loaded segment to a
    # common loudness before appending — this is what actually flattens
    # the Edge/OpenAI/Kokoro volume differences; whole-chapter post-hoc
    # normalization can't do that.
    output = AudioSegment.silent(duration=0)
    manifest: list[dict] = []
    prev_type: SegmentType | None = None
    for seg, mapping in plan:
        if mapping is None:
            output += AudioSegment.silent(duration=_SCENE_BREAK_MS)
            manifest.append(
                {
                    "index": seg.index,
                    "segment_type": seg.segment_type.value,
                    "speaker": seg.speaker,
                    "voice_id": None,
                    "cache_key": None,
                    "path": None,
                }
            )
            prev_type = seg.segment_type
            continue

        text = (
            strip_dialogue_quotes(seg.text)
            if seg.segment_type == SegmentType.DIALOGUE
            else seg.text
        )
        settings = compute_settings(mapping, seg.segment_type, speed_policy)
        key = cache_key(mapping, text, settings)
        seg_path = segments_dir / f"{key}.wav"

        seg_audio = _load_segment_audio(seg_path)
        if normalize:
            seg_audio = _normalize_to_lufs(seg_audio)

        silence = AudioSegment.silent(duration=gap_ms(prev_type, seg.segment_type))
        output += silence + seg_audio

        resolved_speaker = seg.speaker or (
            chapter.pov_character if seg.segment_type == SegmentType.NARRATION else None
        )
        manifest.append(
            {
                "index": seg.index,
                "segment_type": seg.segment_type.value,
                "speaker": seg.speaker,
                "resolved_speaker": resolved_speaker,
                "provider": mapping.provider,
                "voice_id": mapping.voice_id,
                "settings": settings or None,
                "cache_key": key,
                "path": f"segments/{key}.wav",
                "text_preview": text[:80] + ("..." if len(text) > 80 else ""),
                "char_count": len(text),
            }
        )
        if verbose:
            label = resolved_speaker or "-"
            speed = settings.get("speed") or settings.get("rate") or "1.0"
            logger.info(
                "[%04d] %-15s %-22s %-7s %-22s speed=%-6s %4dch",
                seg.index,
                seg.segment_type.value,
                str(label),
                mapping.provider,
                mapping.voice_id,
                str(speed),
                len(text),
            )
        prev_type = seg.segment_type

    # Step 4: atomic export + manifest.
    out_path = chapters_dir / f"chapter_{chapter.chapter_id}.wav"
    with tempfile.NamedTemporaryFile(dir=chapters_dir, suffix=".wav.tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    output.export(tmp_path, format="wav")
    tmp_path.rename(out_path)

    manifest_path = chapters_dir / f"chapter_{chapter.chapter_id}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logger.info(
        "chapter %d: %d segments (%d synthesized, %d cached) -> %s",
        chapter.chapter_number,
        len(chapter.segments),
        synthesized,
        cached_hits,
        out_path,
    )
    return out_path
