"""OpenAI TTS provider — high-quality neural voices.

Uses the OpenAI API's text-to-speech endpoint. Requires OPENAI_API_KEY.
6 voices available, all very natural-sounding.

Voices:
- alloy: neutral, balanced
- ash: warm, conversational male
- echo: smooth, deep male
- fable: expressive, British-accented
- nova: warm, friendly female
- onyx: deep, authoritative male
- shimmer: soft, gentle female
- sage: calm, thoughtful
- coral: warm, natural female
- ballad: soft, melodic

Models:
- tts-1: faster, lower quality (~$0.015/1K chars)
- tts-1-hd: slower, higher quality (~$0.030/1K chars)
"""

from __future__ import annotations

from openai import OpenAI

from .base import TTSSynthesisError


class OpenAITTSProvider:
    """TTS provider using OpenAI's text-to-speech API."""

    def __init__(self, model: str = "tts-1") -> None:
        self._model = model
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI()
        return self._client

    @property
    def name(self) -> str:
        """Provider identifier."""
        return "openai"

    def synthesize(self, text: str, voice_id: str, **settings: object) -> bytes:
        """Synthesize text to WAV audio bytes using OpenAI TTS.

        Args:
            text: Text to synthesize.
            voice_id: OpenAI voice name (e.g., "alloy", "nova", "onyx").
            **settings: Optional params — speed (float, 0.25 to 4.0).

        Returns:
            WAV audio bytes (24 kHz, 16-bit PCM).

        Raises:
            TTSSynthesisError: If the API call fails.
        """
        kwargs: dict[str, object] = {
            "model": self._model,
            "voice": voice_id,
            "input": text,
            "response_format": "wav",
        }
        if "speed" in settings:
            kwargs["speed"] = float(settings["speed"])  # type: ignore[arg-type]

        try:
            response = self._get_client().audio.speech.create(**kwargs)  # type: ignore[arg-type]
            return response.content
        except Exception as e:
            raise TTSSynthesisError(f"OpenAI TTS failed for voice '{voice_id}': {e}") from e


# All available OpenAI TTS voices
OPENAI_VOICES = [
    {"voice_id": "alloy", "gender": "neutral", "description": "Neutral, balanced"},
    {"voice_id": "ash", "gender": "male", "description": "Warm, conversational"},
    {"voice_id": "ballad", "gender": "male", "description": "Soft, melodic"},
    {"voice_id": "coral", "gender": "female", "description": "Warm, natural"},
    {"voice_id": "echo", "gender": "male", "description": "Smooth, deep"},
    {"voice_id": "fable", "gender": "male", "description": "Expressive, British-accented"},
    {"voice_id": "nova", "gender": "female", "description": "Warm, friendly"},
    {"voice_id": "onyx", "gender": "male", "description": "Deep, authoritative"},
    {"voice_id": "sage", "gender": "female", "description": "Calm, thoughtful"},
    {"voice_id": "shimmer", "gender": "female", "description": "Soft, gentle"},
]
