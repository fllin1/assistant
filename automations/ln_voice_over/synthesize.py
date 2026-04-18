"""Stage 8: Synthesize audio from reviewed chapters.

Reads a reviewed Chapter + series VoiceConfig + CharacterRegistry, runs
each segment through its assigned TTS provider, and concatenates the
per-segment MP3s with scene-appropriate silence into a single chapter MP3.

Segments are cached on disk under `audio/segments/<cache_key>.mp3`. The
cache key is `sha256(provider:voice_id:text)[:16]`, so fixing a single
attribution and re-running only re-synthesizes the one changed segment.

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
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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

# Normalization target — a common spoken-word loudness. pydub's dBFS is a
# peak-ish metric (not true LUFS), so this is a coarse flattener between
# providers with different inherent volume, not broadcast-grade loudness.
_TARGET_DBFS = -16.0

# Gap table: (prev_type, curr_type) -> milliseconds. Any pair not listed
# falls back to 400ms (the narration<->narration default).
_GAP_MS: dict[tuple[SegmentType | None, SegmentType], int] = {
    # Scene-break durations are themselves the silence — we don't pad
    # around them, so neighbour pairs involving SCENE_BREAK are skipped
    # here (see gap_ms fallback for anything not in this table).
    (SegmentType.DIALOGUE, SegmentType.DIALOGUE): 200,
    (SegmentType.NARRATION, SegmentType.DIALOGUE): 400,
    (SegmentType.DIALOGUE, SegmentType.NARRATION): 400,
}

_SCENE_BREAK_MS = 800
_CHAPTER_HEADER_LEAD_MS = 1500


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
            return voices.default_narrator
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


def cache_key(mapping: VoiceMapping, text: str) -> str:
    """Content-addressed segment ID. Includes provider so the same voice_id
    on two providers (hypothetical but possible) doesn't collide."""
    payload = f"{mapping.provider}:{mapping.voice_id}:{text}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


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
    return _GAP_MS.get((prev, curr), 400)


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


def synthesize_segment(
    segment: Segment,
    mapping: VoiceMapping,
    cache_dir: Path,
    max_retries: int = 3,
) -> Path:
    """Return the cached MP3 path for a segment. Synthesize on miss.

    Retries TTSSynthesisError with exponential backoff (1s, 2s, 4s) before
    giving up — handles transient rate limits / network blips without a
    dedicated retry dependency.
    """
    text = segment.text
    if segment.segment_type == SegmentType.DIALOGUE:
        text = strip_dialogue_quotes(text)

    key = cache_key(mapping, text)
    out = cache_dir / f"{key}.mp3"
    if out.exists():
        return out

    provider = get_provider(mapping.provider)
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            audio = provider.synthesize(text, mapping.voice_id)
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


def _load_segment_audio(path: Path) -> AudioSegment:
    return AudioSegment.from_mp3(path)


def assemble_chapter(
    chapter: Chapter,
    voices: VoiceConfig,
    registry: CharacterRegistry,
    audio_dir: Path,
    parallel: int = 4,
    normalize: bool = True,
) -> Path:
    """Synthesize every segment then concatenate into one chapter MP3.

    Args:
        chapter: Reviewed chapter with resolved speakers.
        voices: Series-level voice mappings.
        registry: Series-level character registry (for gender lookup).
        audio_dir: Volume's `audio/` directory. Writes into `segments/`
            and `chapters/` subdirs.
        parallel: Max concurrent TTS calls. Drop to 2 for Kokoro-heavy
            chapters — the pipeline singleton serialises anyway.
        normalize: When True, apply `apply_gain(target - dBFS)` to flatten
            provider-to-provider volume differences.

    Returns:
        Path to the assembled `chapters/chapter_NN.mp3`.

    Raises:
        TTSSynthesisError: If synthesis fails after all retries on any
            segment.
    """
    segments_dir = audio_dir / "segments"
    chapters_dir = audio_dir / "chapters"
    segments_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: resolve voice for each segment.
    plan: list[tuple[Segment, VoiceMapping | None]] = [
        (seg, resolve_voice(seg, chapter, voices, registry)) for seg in chapter.segments
    ]

    # Step 2: dedupe by cache_key (same line by same voice = one TTS call)
    # and fire them in parallel. Segments with None mapping (scene breaks)
    # are synthesized as silence at assembly time, not here.
    work: dict[str, tuple[Segment, VoiceMapping]] = {}
    for seg, mapping in plan:
        if mapping is None:
            continue
        text = (
            strip_dialogue_quotes(seg.text)
            if seg.segment_type == SegmentType.DIALOGUE
            else seg.text
        )
        key = cache_key(mapping, text)
        work.setdefault(key, (seg, mapping))

    # Cache hits are decided up-front so we can report sensible counts and
    # avoid even submitting work for segments that already have MP3s.
    pending: list[tuple[str, Segment, VoiceMapping]] = []
    cached_hits = 0
    for key, (seg, mapping) in work.items():
        if (segments_dir / f"{key}.mp3").exists():
            cached_hits += 1
        else:
            pending.append((key, seg, mapping))

    synthesized = 0
    if pending:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = [
                pool.submit(synthesize_segment, seg, mapping, segments_dir)
                for _, seg, mapping in pending
            ]
            for future in futures:
                future.result()  # re-raises TTSSynthesisError if retries exhausted
                synthesized += 1

    # Step 3: concatenate in order with gaps and scene-break silences.
    output = AudioSegment.silent(duration=0)
    manifest: list[dict] = []
    prev_type: SegmentType | None = None
    for seg, mapping in plan:
        if mapping is None:
            # SCENE_BREAK -> pure silence, no TTS
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
        key = cache_key(mapping, text)
        seg_path = segments_dir / f"{key}.mp3"

        silence = AudioSegment.silent(duration=gap_ms(prev_type, seg.segment_type))
        output += silence + _load_segment_audio(seg_path)

        manifest.append(
            {
                "index": seg.index,
                "segment_type": seg.segment_type.value,
                "speaker": seg.speaker,
                "voice_id": mapping.voice_id,
                "cache_key": key,
                "path": f"segments/{key}.mp3",
            }
        )
        prev_type = seg.segment_type

    # Step 4: optional gain normalisation to target dBFS.
    if normalize and output.dBFS != float("-inf"):
        output = output.apply_gain(_TARGET_DBFS - output.dBFS)

    # Step 5: atomic export + manifest.
    out_path = chapters_dir / f"chapter_{chapter.chapter_number:02d}.mp3"
    with tempfile.NamedTemporaryFile(dir=chapters_dir, suffix=".mp3.tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    output.export(tmp_path, format="mp3")
    tmp_path.rename(out_path)

    manifest_path = chapters_dir / f"chapter_{chapter.chapter_number:02d}.manifest.json"
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
