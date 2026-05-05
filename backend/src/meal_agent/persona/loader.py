"""Voice-pack loader.

Loads YAML pack files from the configured directory, validates against
`VoicePack`, and caches in-process. Hot-reload is intentionally not supported
in v1 — packs are deployed with the service.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path

import yaml

from meal_agent.persona.schema import VoicePack
from meal_agent.settings import get_settings


class VoicePackNotFound(Exception):
    """Raised when a voice_pack_id cannot be resolved."""


_lock = threading.Lock()


@lru_cache(maxsize=32)
def load_pack(voice_pack_id: str) -> VoicePack:
    """Load and validate a voice pack by id.

    Looks for `<settings.persona_packs_dir>/<voice_pack_id>.yaml`.
    Raises `VoicePackNotFound` if missing.
    Cached in-process — call `clear_cache()` to refresh.
    """
    settings = get_settings()
    path: Path = settings.persona_packs_dir / f"{voice_pack_id}.yaml"

    with _lock:
        if not path.is_file():
            raise VoicePackNotFound(
                f"Voice pack '{voice_pack_id}' not found at {path}"
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    return VoicePack.model_validate(raw)


def clear_cache() -> None:
    """Drop the in-process pack cache. Useful in tests + future hot-reload."""
    load_pack.cache_clear()


__all__ = ["VoicePackNotFound", "clear_cache", "load_pack"]
