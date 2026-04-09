"""TTSProvider protocol — the interface all TTS providers implement.

Uses typing.Protocol for structural subtyping (duck typing with type
checker support). Providers don't need to inherit from anything — they
just need to have the right methods.

Example usage:
    provider = EdgeTTSProvider()
    audio_bytes = provider.synthesize("Hello world", "en-US-GuyNeural")
"""

from __future__ import annotations

from typing import Protocol


class TTSProvider(Protocol):
    """Protocol for TTS provider implementations.

    Any class with a matching synthesize() method and name property
    satisfies this protocol — no inheritance required.
    """

    @property
    def name(self) -> str:
        """Provider identifier (e.g., "edge", "elevenlabs")."""
        ...

    def synthesize(
        self, text: str, voice_id: str, **settings: object
    ) -> bytes:
        """Convert text to audio bytes.

        Args:
            text: The text to synthesize.
            voice_id: Provider-specific voice identifier.
            **settings: Optional provider-specific parameters
                (speed, pitch, stability, etc.).

        Returns:
            Raw audio bytes (MP3 format preferred).

        Raises:
            TTSSynthesisError: If the provider fails to generate audio.
        """
        ...


class TTSSynthesisError(Exception):
    """Raised when a TTS provider fails to synthesize audio."""
