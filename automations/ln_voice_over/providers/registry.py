"""TTS provider registry — maps provider name strings to implementations.

This is the factory for TTS providers. VoiceMapping stores a provider
name (e.g., "edge"), and get_provider() turns that into a live
TTSProvider instance.

To add a new provider:
1. Create a new module in providers/ implementing TTSProvider
2. Add a single entry to _REGISTRY below
"""

from __future__ import annotations

from .base import TTSProvider
from .edge import EdgeTTSProvider
from .kokoro import KokoroTTSProvider
from .openai import OpenAITTSProvider

_REGISTRY: dict[str, type] = {
    "edge": EdgeTTSProvider,
    "kokoro": KokoroTTSProvider,
    "openai": OpenAITTSProvider,
}


def get_provider(name: str) -> TTSProvider:
    """Resolve a provider name to a provider instance.

    Args:
        name: Provider key from VoiceMapping.provider (e.g., "edge").

    Returns:
        An initialized TTSProvider instance.

    Raises:
        KeyError: If the provider name is not registered.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown TTS provider '{name}'. Available: {available}")
    return _REGISTRY[name]()
