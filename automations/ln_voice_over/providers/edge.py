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


class EdgeTTSProvider:
    """TTS provider using Microsoft Edge's free neural voices.

    Wraps the async edge-tts library in a synchronous interface.
    Uses asyncio.run() internally for each synthesis call.
    """

    @property
    def name(self) -> str:
        """Provider identifier."""
        return "edge"

    def synthesize(
        self, text: str, voice_id: str, **settings: object
    ) -> bytes:
        """Synthesize text to MP3 audio bytes using Edge TTS.

        Creates an edge_tts.Communicate instance, runs the async
        synthesis, and collects the audio bytes.

        Args:
            text: Text to synthesize.
            voice_id: Edge voice name (e.g., "en-US-GuyNeural").
            **settings: Optional params — rate (str, e.g. "+10%"),
                pitch (str, e.g. "+5Hz"), volume (str, e.g. "-10%").

        Returns:
            MP3 audio bytes.

        Raises:
            TTSSynthesisError: If edge-tts fails.
        """
        ...
