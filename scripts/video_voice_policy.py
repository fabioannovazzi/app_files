from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

__all__ = [
    "APPROVED_VIDEO_VOICES",
    "OPENAI_VIDEO_TTS_MODEL",
    "SUPPORTED_VIDEO_LANGUAGES",
    "VIDEO_VOICE_BY_LANGUAGE",
    "video_voice_for_language",
]

OPENAI_VIDEO_TTS_MODEL = "gpt-4o-mini-tts"
VIDEO_VOICE_BY_LANGUAGE: Mapping[str, str] = MappingProxyType(
    {
        "it": "marin",
        "en": "cedar",
        "fr": "cedar",
        "de": "cedar",
        "es": "cedar",
    }
)
APPROVED_VIDEO_VOICES = frozenset(VIDEO_VOICE_BY_LANGUAGE.values())
SUPPORTED_VIDEO_LANGUAGES = frozenset(VIDEO_VOICE_BY_LANGUAGE)


def video_voice_for_language(language: str) -> str:
    """Return the only approved narration voice for a video language."""

    normalized = language.strip().lower()
    try:
        return VIDEO_VOICE_BY_LANGUAGE[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported video language: {language!r}") from exc
