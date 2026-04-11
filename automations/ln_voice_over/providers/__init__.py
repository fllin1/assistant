"""TTS provider implementations.

Each provider module exports a class implementing the TTSProvider protocol
defined in base.py. The provider is selected by the voice_config's provider
field on each VoiceMapping.
"""

from .registry import get_provider

__all__ = ["get_provider"]
