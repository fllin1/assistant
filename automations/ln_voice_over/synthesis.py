"""SYNTHESIS-stage planning and WAV rendering for reviewed chapters."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import threading
import wave
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AUDIO_GAP_MS_BY_TRANSITION, DEFAULT_AUDIO_GAP_MS, SCENE_BREAK_SILENCE_MS
from .models import Chapter, CharacterRegistry, Segment, SegmentType
from .review import ReviewValidationError, validate_reviewed_chapter
from .voice_mapping import VoiceMapping, VoiceMappingEntry

DEFAULT_SAMPLE_RATE = 24_000
DEFAULT_SAMPLE_WIDTH = 2
DEFAULT_CHANNELS = 1
ProgressEvent = dict[str, Any]
ProgressCallback = Callable[[ProgressEvent], None]

QUOTE_PAIRS = (
    ('"', '"'),
    ("'", "'"),
    ("\u201c", "\u201d"),
    ("\u2018", "\u2019"),
)


class SynthesisError(RuntimeError):
    """Raised when synthesis cannot complete."""


class SynthesisPreflightError(SynthesisError):
    """Raised when strict synthesis preflight finds blocking problems."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        message = "SYNTHESIS preflight failed:\n" + "\n".join(f"- {p}" for p in problems)
        super().__init__(message)


@dataclass(frozen=True)
class EngineInfo:
    """Voice-tuning engine availability and cache-version metadata."""

    name: str
    version: str
    available: bool
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class SegmentSynthesisPlan:
    """Audio plan for one reviewed segment."""

    index: int
    segment_type: SegmentType
    speaker: str | None
    voice_key: str | None
    prepared_text: str
    engine: str | None
    voice_id: str | None
    speed: float | None
    params: dict[str, Any]
    playback_speed: float | None
    cache_key: str | None
    cache_path: Path | None
    stem_path: Path
    cache_hit: bool
    silence_ms: int = 0

    @property
    def needs_tts(self) -> bool:
        return self.engine is not None and self.cache_path is not None


@dataclass(frozen=True)
class SynthesisPlan:
    """A complete chapter render plan after strict preflight."""

    chapter_id: str
    volume_path: Path
    output_path: Path
    manifest_path: Path
    segments: tuple[SegmentSynthesisPlan, ...]

    @property
    def cache_hits(self) -> int:
        return sum(1 for segment in self.segments if segment.needs_tts and segment.cache_hit)

    @property
    def cache_misses(self) -> int:
        return sum(1 for segment in self.segments if segment.needs_tts and not segment.cache_hit)


class VoiceTuningBridge:
    """Subprocess bridge into the companion voice-tuning uv project."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def inspect_engines(self) -> dict[str, EngineInfo]:
        """Probe voice-tuning engines without generating audio."""
        script = """
import json
from backend.engines.registry import get_engines

payload = {}
for name, engine in get_engines().items():
    payload[name] = {
        "name": name,
        "version": getattr(engine, "version", "v1"),
        "available": bool(getattr(engine, "available", False)),
        "unavailable_reason": getattr(engine, "unavailable_reason", None),
    }
print(json.dumps(payload))
"""
        payload = self._run_json_script(script, None)
        return {
            name: EngineInfo(
                name=value["name"],
                version=value["version"],
                available=value["available"],
                unavailable_reason=value.get("unavailable_reason"),
            )
            for name, value in payload.items()
        }

    def render_segments(
        self,
        requests: list[dict[str, Any]],
        progress: ProgressCallback | None = None,
    ) -> dict[int, bytes]:
        """Render TTS WAV bytes through voice-tuning engines."""
        script = """
import asyncio
import base64
import json
import sys

from backend.engines.registry import get_engine

async def main():
    payload = json.load(sys.stdin)
    rendered = []
    segments = payload["segments"]
    total = len(segments)
    for ordinal, item in enumerate(segments, start=1):
        print(json.dumps({
            "event": "render_segment_start",
            "ordinal": ordinal,
            "total": total,
            "index": item["index"],
            "engine": item["engine"],
            "voice_key": item.get("voice_key"),
            "text_chars": len(item["text"]),
        }), file=sys.stderr, flush=True)
        engine = get_engine(item["engine"])
        audio = await engine.generate(
            item["text"],
            item["voice_id"],
            speed=item.get("speed", 1.0),
            params=item.get("params") or {},
        )
        print(json.dumps({
            "event": "render_segment_done",
            "ordinal": ordinal,
            "total": total,
            "index": item["index"],
            "engine": item["engine"],
            "audio_bytes": len(audio),
        }), file=sys.stderr, flush=True)
        rendered.append({
            "index": item["index"],
            "audio_b64": base64.b64encode(audio).decode("ascii"),
        })
    print(json.dumps({"segments": rendered}))

asyncio.run(main())
"""
        payload = self._run_json_script_streaming(script, {"segments": requests}, progress)
        return {
            int(item["index"]): base64.b64decode(item["audio_b64"]) for item in payload["segments"]
        }

    def _run_json_script(self, script: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not self.root.exists():
            raise SynthesisError(f"voice-tuning root not found: {self.root}")
        try:
            result = subprocess.run(
                ["uv", "run", "python", "-c", script],
                cwd=self.root,
                input=json.dumps(payload) if payload is not None else None,
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SynthesisError("uv command not found; cannot run voice-tuning bridge") from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise SynthesisError(f"voice-tuning bridge failed: {stderr}")
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise SynthesisError("voice-tuning bridge returned no JSON")
        return json.loads(lines[-1])

    def _run_json_script_streaming(
        self,
        script: str,
        payload: dict[str, Any],
        progress: ProgressCallback | None,
    ) -> dict[str, Any]:
        if not self.root.exists():
            raise SynthesisError(f"voice-tuning root not found: {self.root}")
        try:
            process = subprocess.Popen(
                ["uv", "run", "python", "-c", script],
                cwd=self.root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise SynthesisError("uv command not found; cannot run voice-tuning bridge") from exc

        stdout_chunks: list[str] = []
        stderr_lines: list[str] = []
        reader_errors: list[BaseException] = []

        def read_stdout() -> None:
            try:
                assert process.stdout is not None
                stdout_chunks.append(process.stdout.read())
            except BaseException as exc:
                reader_errors.append(exc)

        def read_stderr() -> None:
            try:
                assert process.stderr is not None
                for line in process.stderr:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    event = _decode_progress_event(stripped)
                    if progress and event is not None:
                        progress(event)
                    else:
                        stderr_lines.append(stripped)
            except BaseException as exc:
                reader_errors.append(exc)

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        try:
            assert process.stdin is not None
            process.stdin.write(json.dumps(payload))
            process.stdin.close()
        except BrokenPipeError:
            pass

        returncode = process.wait()
        stdout_thread.join()
        stderr_thread.join()

        if reader_errors:
            raise SynthesisError(f"voice-tuning bridge output reader failed: {reader_errors[0]}")

        stdout = "".join(stdout_chunks)
        if returncode != 0:
            stderr = "\n".join(stderr_lines) or stdout.strip()
            raise SynthesisError(f"voice-tuning bridge failed: {stderr}")
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            raise SynthesisError("voice-tuning bridge returned no JSON")
        return json.loads(lines[-1])


def _decode_progress_event(line: str) -> ProgressEvent | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict) and isinstance(value.get("event"), str):
        return value
    return None


def normalize_chapter_id(chapter_id: str) -> str:
    """Normalize CLI chapter ids to the `chapter_<id>.json` suffix."""
    value = chapter_id.strip()
    if value.endswith(".json"):
        value = value[:-5]
    if value.startswith("chapter_"):
        value = value.removeprefix("chapter_")
    if value.isdigit():
        return f"{int(value):02d}"
    return value


def reviewed_chapter_path(volume_path: Path, chapter_id: str) -> Path:
    """Return the reviewed chapter path for a CLI chapter id."""
    return volume_path / "reviewed" / f"chapter_{normalize_chapter_id(chapter_id)}.json"


def prepare_tts_text(segment: Segment) -> str:
    """Prepare segment text for TTS without changing canonical data."""
    if segment.segment_type != SegmentType.DIALOGUE:
        return segment.text

    text = segment.text.strip()
    for opener, closer in QUOTE_PAIRS:
        if len(text) >= 2 and text.startswith(opener) and text.endswith(closer):
            return text[1:-1].strip()
    return text


def build_synthesis_plan(
    chapter: Chapter,
    registry: CharacterRegistry,
    voice_mapping: VoiceMapping,
    volume_path: Path,
    chapter_id: str,
    engine_infos: dict[str, EngineInfo],
) -> SynthesisPlan:
    """Validate inputs and return a complete render plan."""
    problems: list[str] = []
    try:
        validate_reviewed_chapter(chapter, registry)
    except ReviewValidationError as exc:
        problems.extend(exc.problems)

    normalized_id = normalize_chapter_id(chapter_id)
    audio_root = volume_path / "audio"
    cache_dir = audio_root / "cache"
    stems_dir = audio_root / f"chapter_{normalized_id}"
    output_path = audio_root / f"chapter_{normalized_id}.wav"
    manifest_path = audio_root / f"chapter_{normalized_id}.manifest.json"
    planned_segments: list[SegmentSynthesisPlan] = []

    for segment in chapter.segments:
        stem_path = stems_dir / f"segment_{segment.index}.wav"
        if segment.segment_type == SegmentType.SCENE_BREAK:
            planned_segments.append(
                SegmentSynthesisPlan(
                    index=segment.index,
                    segment_type=segment.segment_type,
                    speaker=segment.speaker,
                    voice_key=None,
                    prepared_text="",
                    engine=None,
                    voice_id=None,
                    speed=None,
                    params={},
                    playback_speed=None,
                    cache_key=None,
                    cache_path=None,
                    stem_path=stem_path,
                    cache_hit=False,
                    silence_ms=SCENE_BREAK_SILENCE_MS,
                )
            )
            continue

        voice_key = voice_key_for_segment(chapter, segment)
        entry = voice_mapping.get(voice_key) if voice_key else None
        if voice_key is None:
            problems.append(f"segment {segment.index} has no voice key")
            continue
        if entry is None:
            problems.append(f"voice mapping missing key: {voice_key!r}")
            continue

        prepared_text = prepare_tts_text(segment)
        if not prepared_text:
            problems.append(f"segment {segment.index} has empty TTS text")
            continue

        engine = engine_infos.get(entry.engine)
        if engine is None:
            problems.append(f"voice-tuning engine is unknown: {entry.engine!r}")
            engine_version = "unknown"
        elif not engine.available:
            reason = engine.unavailable_reason or "unavailable"
            problems.append(f"voice-tuning engine {entry.engine!r} unavailable: {reason}")
            engine_version = engine.version
        else:
            engine_version = engine.version

        cache_key = synthesis_cache_key(
            engine_version=engine_version,
            entry=entry,
            text=prepared_text,
            segment_type=segment.segment_type,
        )
        cache_path = cache_dir / f"{cache_key}.wav"
        planned_segments.append(
            SegmentSynthesisPlan(
                index=segment.index,
                segment_type=segment.segment_type,
                speaker=segment.speaker,
                voice_key=voice_key,
                prepared_text=prepared_text,
                engine=entry.engine,
                voice_id=entry.voice_id,
                speed=entry.speed,
                params=dict(entry.params),
                playback_speed=entry.playback_speed,
                cache_key=cache_key,
                cache_path=cache_path,
                stem_path=stem_path,
                cache_hit=cache_path.exists(),
            )
        )

    if problems:
        raise SynthesisPreflightError(problems)

    return SynthesisPlan(
        chapter_id=normalized_id,
        volume_path=volume_path,
        output_path=output_path,
        manifest_path=manifest_path,
        segments=tuple(planned_segments),
    )


def voice_key_for_segment(chapter: Chapter, segment: Segment) -> str | None:
    """Resolve a reviewed segment to the voice mapping key synthesis should read."""
    if segment.segment_type == SegmentType.SCENE_BREAK:
        return None
    if segment.speaker == "Narrator":
        return chapter.narrator or "Narrator"
    return segment.speaker


def synthesis_cache_key(
    *,
    engine_version: str,
    entry: VoiceMappingEntry,
    text: str,
    segment_type: SegmentType,
) -> str:
    """Return the content-addressed WAV cache key for one rendered segment."""
    payload = {
        "engine_version": engine_version,
        "engine": entry.engine,
        "voice_id": entry.voice_id,
        "speed": round(entry.speed, 4),
        "params": entry.params,
        "text": text,
        "segment_type": segment_type.value,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def render_synthesis_plan(
    plan: SynthesisPlan,
    bridge: VoiceTuningBridge,
    progress: ProgressCallback | None = None,
) -> None:
    """Render missing stems, refresh chapter stems, concatenate, and write manifest."""
    missing = [segment for segment in plan.segments if segment.needs_tts and not segment.cache_hit]
    if missing:
        if progress:
            progress({"event": "render_batch_start", "total": len(missing)})
        requests = [
            {
                "index": segment.index,
                "engine": segment.engine,
                "voice_id": segment.voice_id,
                "voice_key": segment.voice_key,
                "speed": segment.speed,
                "params": segment.params,
                "text": segment.prepared_text,
            }
            for segment in missing
        ]
        rendered = bridge.render_segments(requests, progress=progress)
        if progress:
            progress({"event": "render_batch_done", "total": len(missing)})
        for segment in missing:
            audio = rendered.get(segment.index)
            if audio is None:
                raise SynthesisError(f"voice-tuning did not render segment {segment.index}")
            assert segment.cache_path is not None
            segment.cache_path.parent.mkdir(parents=True, exist_ok=True)
            segment.cache_path.write_bytes(audio)
    elif progress:
        progress({"event": "render_batch_cached"})

    if progress:
        progress({"event": "stems_start"})
    _refresh_chapter_stems(plan)
    if progress:
        progress({"event": "concat_start", "output": str(plan.output_path)})
    _concatenate_chapter(plan)
    _write_manifest(plan)


def format_render_plan(plan: SynthesisPlan) -> str:
    """Return a concise human-readable render plan."""
    engine_counts = Counter(
        segment.engine for segment in plan.segments if segment.needs_tts and segment.engine
    )
    hume_segments = [segment for segment in plan.segments if segment.engine == "hume"]
    hume_voice_keys = sorted({segment.voice_key for segment in hume_segments if segment.voice_key})
    lines = [
        f"Chapter: {plan.chapter_id}",
        f"Output: {plan.output_path}",
        f"Renderable segments: {sum(1 for s in plan.segments if s.needs_tts)}",
        f"Cache hits: {plan.cache_hits}",
        f"Cache misses: {plan.cache_misses}",
    ]
    if engine_counts:
        lines.append("Segments by engine:")
        for engine, count in sorted(engine_counts.items()):
            lines.append(f"  {engine}: {count}")
    lines.append(f"Hume segments: {len(hume_segments)}")
    if hume_voice_keys:
        lines.append("Hume voice keys: " + ", ".join(hume_voice_keys))
    return "\n".join(lines)


def gap_ms_between(left: SegmentType, right: SegmentType) -> int:
    """Return configured silence between two adjacent segment types."""
    return AUDIO_GAP_MS_BY_TRANSITION.get(
        (left.value, right.value),
        DEFAULT_AUDIO_GAP_MS,
    )


def _refresh_chapter_stems(plan: SynthesisPlan) -> None:
    params = _first_tts_wav_params(plan)
    for segment in plan.segments:
        segment.stem_path.parent.mkdir(parents=True, exist_ok=True)
        if segment.segment_type == SegmentType.SCENE_BREAK:
            _write_silence_wav(segment.stem_path, segment.silence_ms, params)
            continue
        if segment.cache_path is None:
            raise SynthesisError(f"segment {segment.index} has no cache path")
        shutil.copyfile(segment.cache_path, segment.stem_path)


def _concatenate_chapter(plan: SynthesisPlan) -> None:
    params = _first_tts_wav_params(plan)
    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(plan.output_path), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        for index, segment in enumerate(plan.segments):
            _append_wav(out, segment.stem_path, params)
            if index == len(plan.segments) - 1:
                continue
            next_segment = plan.segments[index + 1]
            gap_ms = gap_ms_between(segment.segment_type, next_segment.segment_type)
            out.writeframes(_silence_frames(gap_ms, params))


def _write_manifest(plan: SynthesisPlan) -> None:
    payload = {
        "chapter_id": plan.chapter_id,
        "output": str(plan.output_path),
        "segments": [
            {
                "index": segment.index,
                "segment_type": segment.segment_type.value,
                "speaker": segment.speaker,
                "voice_key": segment.voice_key,
                "engine": segment.engine,
                "voice_id": segment.voice_id,
                "cache_key": segment.cache_key,
                "cache_hit": segment.cache_hit,
                "stem": str(segment.stem_path),
                "silence_ms": segment.silence_ms,
            }
            for segment in plan.segments
        ],
    }
    plan.manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class WavParams:
    """WAV format parameters needed for concat and generated silence."""

    nchannels: int
    sampwidth: int
    framerate: int


def _first_tts_wav_params(plan: SynthesisPlan) -> WavParams:
    for segment in plan.segments:
        path = segment.cache_path if segment.cache_path is not None else segment.stem_path
        if segment.needs_tts and path.exists():
            return _read_wav_params(path)
    return WavParams(
        nchannels=DEFAULT_CHANNELS,
        sampwidth=DEFAULT_SAMPLE_WIDTH,
        framerate=DEFAULT_SAMPLE_RATE,
    )


def _read_wav_params(path: Path) -> WavParams:
    with wave.open(str(path), "rb") as wav:
        return WavParams(
            nchannels=wav.getnchannels(),
            sampwidth=wav.getsampwidth(),
            framerate=wav.getframerate(),
        )


def _append_wav(out: wave.Wave_write, path: Path, expected: WavParams) -> None:
    with wave.open(str(path), "rb") as wav:
        actual = WavParams(
            nchannels=wav.getnchannels(),
            sampwidth=wav.getsampwidth(),
            framerate=wav.getframerate(),
        )
        if actual != expected:
            raise SynthesisError(
                f"WAV format mismatch in {path}: expected {expected}, got {actual}"
            )
        out.writeframes(wav.readframes(wav.getnframes()))


def _write_silence_wav(path: Path, duration_ms: int, params: WavParams) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(params.nchannels)
        wav.setsampwidth(params.sampwidth)
        wav.setframerate(params.framerate)
        wav.writeframes(_silence_frames(duration_ms, params))


def _silence_frames(duration_ms: int, params: WavParams) -> bytes:
    frame_count = int(params.framerate * duration_ms / 1000)
    return b"\x00" * frame_count * params.nchannels * params.sampwidth
