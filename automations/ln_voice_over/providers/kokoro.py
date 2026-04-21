"""Kokoro TTS provider — local, free, high-quality neural voices.

Uses the Kokoro-82M model from HuggingFace. Runs entirely locally,
no API key needed. 20 American English voices (11 female, 9 male)
plus British English voices.

Voices use prefix conventions:
- af_* = American female
- am_* = American male
- bf_* = British female
- bm_* = British male

Requires: kokoro, soundfile, espeak-ng (system package)
"""

from __future__ import annotations

import io
import struct
import wave

import torch

from .base import TTSSynthesisError

# Singleton pipeline — loaded once on first use (~2s cold start)
_pipeline = None
_SAMPLE_RATE = 24000


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from kokoro import KPipeline

        _pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return _pipeline


def _audio_tensor_to_wav(audio: torch.Tensor, sample_rate: int = _SAMPLE_RATE) -> bytes:
    """Convert a 1D float audio tensor to 16-bit PCM WAV bytes."""
    audio_np = (audio.numpy() * 32767).astype("int16")
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack(f"<{len(audio_np)}h", *audio_np))
    return wav_buffer.getvalue()


class KokoroTTSProvider:
    """TTS provider using the local Kokoro-82M model."""

    @property
    def name(self) -> str:
        """Provider identifier."""
        return "kokoro"

    def synthesize(self, text: str, voice_id: str, **settings: object) -> bytes:
        """Synthesize text to WAV audio bytes using Kokoro TTS.

        Args:
            text: Text to synthesize.
            voice_id: Kokoro voice name (e.g., "af_heart", "am_adam").
            **settings: Optional params — speed (float, default 1.0).

        Returns:
            WAV audio bytes (24 kHz, 16-bit mono PCM).

        Raises:
            TTSSynthesisError: If synthesis fails.
        """
        speed = float(settings.get("speed", 1.0)) if "speed" in settings else 1.0
        pipeline = _get_pipeline()

        try:
            # Collect all audio chunks from the generator
            chunks: list[torch.Tensor] = []
            for result in pipeline(text, voice=voice_id, speed=speed):
                chunks.append(result.audio)

            if not chunks:
                raise TTSSynthesisError(f"Kokoro returned no audio for voice '{voice_id}'")

            audio = torch.cat(chunks)
            return _audio_tensor_to_wav(audio)
        except TTSSynthesisError:
            raise
        except Exception as e:
            raise TTSSynthesisError(f"Kokoro TTS failed for voice '{voice_id}': {e}") from e


# Available Kokoro voices (American + British English)
KOKORO_VOICES = [
    # American female
    {
        "voice_id": "af_alloy",
        "gender": "female",
        "accent": "american",
        "description": "Neutral, clear",
    },
    {
        "voice_id": "af_aoede",
        "gender": "female",
        "accent": "american",
        "description": "Melodic, warm",
    },
    {
        "voice_id": "af_bella",
        "gender": "female",
        "accent": "american",
        "description": "Smooth, confident",
    },
    {
        "voice_id": "af_heart",
        "gender": "female",
        "accent": "american",
        "description": "Warm, expressive",
    },
    {
        "voice_id": "af_jessica",
        "gender": "female",
        "accent": "american",
        "description": "Bright, articulate",
    },
    {
        "voice_id": "af_kore",
        "gender": "female",
        "accent": "american",
        "description": "Steady, composed",
    },
    {
        "voice_id": "af_nicole",
        "gender": "female",
        "accent": "american",
        "description": "Soft, gentle",
    },
    {
        "voice_id": "af_nova",
        "gender": "female",
        "accent": "american",
        "description": "Vibrant, energetic",
    },
    {
        "voice_id": "af_river",
        "gender": "female",
        "accent": "american",
        "description": "Calm, flowing",
    },
    {
        "voice_id": "af_sarah",
        "gender": "female",
        "accent": "american",
        "description": "Friendly, natural",
    },
    {"voice_id": "af_sky", "gender": "female", "accent": "american", "description": "Light, airy"},
    # American male
    {
        "voice_id": "am_adam",
        "gender": "male",
        "accent": "american",
        "description": "Balanced, natural",
    },
    {
        "voice_id": "am_echo",
        "gender": "male",
        "accent": "american",
        "description": "Deep, resonant",
    },
    {"voice_id": "am_eric", "gender": "male", "accent": "american", "description": "Warm, steady"},
    {
        "voice_id": "am_fenrir",
        "gender": "male",
        "accent": "american",
        "description": "Strong, intense",
    },
    {
        "voice_id": "am_liam",
        "gender": "male",
        "accent": "american",
        "description": "Young, energetic",
    },
    {
        "voice_id": "am_michael",
        "gender": "male",
        "accent": "american",
        "description": "Mature, authoritative",
    },
    {
        "voice_id": "am_onyx",
        "gender": "male",
        "accent": "american",
        "description": "Deep, commanding",
    },
    {
        "voice_id": "am_puck",
        "gender": "male",
        "accent": "american",
        "description": "Playful, mischievous",
    },
    # British female
    {
        "voice_id": "bf_alice",
        "gender": "female",
        "accent": "british",
        "description": "Refined, clear",
    },
    {
        "voice_id": "bf_emma",
        "gender": "female",
        "accent": "british",
        "description": "Warm, composed",
    },
    {
        "voice_id": "bf_isabella",
        "gender": "female",
        "accent": "british",
        "description": "Elegant, poised",
    },
    {
        "voice_id": "bf_lily",
        "gender": "female",
        "accent": "british",
        "description": "Soft, gentle",
    },
    # British male
    {
        "voice_id": "bm_daniel",
        "gender": "male",
        "accent": "british",
        "description": "Steady, clear",
    },
    {
        "voice_id": "bm_fable",
        "gender": "male",
        "accent": "british",
        "description": "Expressive, theatrical",
    },
    {
        "voice_id": "bm_george",
        "gender": "male",
        "accent": "british",
        "description": "Deep, mature",
    },
    {"voice_id": "bm_lewis", "gender": "male", "accent": "british", "description": "Young, warm"},
]
