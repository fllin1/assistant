"""Edge TTS provider — free Microsoft neural voices.

Uses the edge-tts library (async) wrapped in a sync interface.
No API key needed. Voices are Microsoft Azure neural voices accessed
through the Edge browser's TTS endpoint.

Popular voices:
- en-US-GuyNeural (male, natural)
- en-US-JennyNeural (female, natural)
- en-US-AriaNeural (female, expressive)
- en-US-DavisNeural (male, calm)
- en-GB-RyanNeural (male, British)
- en-GB-SoniaNeural (female, British)

List all available voices: edge-tts --list-voices
"""

from __future__ import annotations

import asyncio
import io

import edge_tts

from .base import TTSSynthesisError


class EdgeTTSProvider:
    """TTS provider using Microsoft Edge's free neural voices.

    Wraps the async edge-tts library in a synchronous interface.
    Uses asyncio.run() internally for each synthesis call.
    """

    @property
    def name(self) -> str:
        """Provider identifier."""
        return "edge"

    def synthesize(self, text: str, voice_id: str, **settings: object) -> bytes:
        """Synthesize text to WAV audio bytes using Edge TTS.

        Edge only exposes MP3 from its stream, so we decode that MP3 to
        WAV once inside the provider to keep the downstream pipeline
        PCM-native. The decode itself is lossless; the only lossy step
        is Edge's server-side MP3 encode which we can't avoid.

        Args:
            text: Text to synthesize.
            voice_id: Edge voice name (e.g., "en-US-GuyNeural").
            **settings: Optional params — rate (str, e.g. "+10%"),
                pitch (str, e.g. "+5Hz"), volume (str, e.g. "-10%").

        Returns:
            WAV audio bytes.

        Raises:
            TTSSynthesisError: If edge-tts fails.
        """
        communicate_kwargs: dict[str, str] = {}
        for key in ("rate", "pitch", "volume"):
            if key in settings:
                communicate_kwargs[key] = str(settings[key])

        async def _synthesize() -> bytes:
            communicate = edge_tts.Communicate(text, voice_id, **communicate_kwargs)
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        try:
            mp3_bytes = asyncio.run(_synthesize())
        except Exception as e:
            raise TTSSynthesisError(f"Edge TTS failed for voice '{voice_id}': {e}") from e

        if not mp3_bytes:
            raise TTSSynthesisError(f"Edge TTS returned empty audio for voice '{voice_id}'")

        # Decode Edge's MP3 to WAV once. Import pydub lazily so the rest
        # of the providers (Kokoro/OpenAI paths) don't pay the import cost.
        from pydub import AudioSegment

        try:
            segment = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
            wav_buffer = io.BytesIO()
            segment.export(wav_buffer, format="wav")
            return wav_buffer.getvalue()
        except Exception as e:
            raise TTSSynthesisError(
                f"Edge TTS: failed to decode MP3 to WAV for voice '{voice_id}': {e}"
            ) from e


async def list_edge_voices(
    locale_prefix: str = "en-",
    gender: str | None = None,
) -> list[dict[str, str]]:
    """List available Edge TTS voices, optionally filtered.

    Args:
        locale_prefix: Filter voices by locale prefix (e.g. "en-", "en-US").
        gender: Filter by "Male" or "Female" (case-insensitive).

    Returns:
        List of voice dicts with ShortName, Gender, Locale keys.
    """
    voices = await edge_tts.list_voices()
    filtered = [v for v in voices if v["Locale"].startswith(locale_prefix)]
    if gender:
        filtered = [v for v in filtered if v["Gender"].lower() == gender.lower()]
    return filtered
