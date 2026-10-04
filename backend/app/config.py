"""Central application settings.

Tuning valves live in ``backend/config.toml`` (parsed with stdlib
``tomllib``, no new dependency). Environment variables — e.g. those in
``backend/.env`` — override the file. Secrets stay in the environment.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_PATH = Path(os.environ.get("BOOKREADER_CONFIG", Path(__file__).resolve().parent.parent / "config.toml"))


def _file_values() -> dict:
    try:
        with open(_CONFIG_PATH, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    merged: dict = {}
    for section in data.values():
        if isinstance(section, dict):
            merged.update(section)
    return merged


_FILE_DEFAULTS = _file_values()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = "http://localhost:8000"
    supabase_service_role_key: str = "replace-me"
    openai_api_key: str = "replace-me"
    openai_segmentation_model: str = _FILE_DEFAULTS.get("segmentation_model", "gpt-4o-mini")
    openai_tts_model: str = _FILE_DEFAULTS.get("tts_model", "tts-1")
    openai_tts_voice: str = _FILE_DEFAULTS.get("tts_voice", "alloy")
    # Token limit: per-request output cap for segmentation. Defaults to the
    # 3000-token budget in config.toml.
    openai_segmentation_max_tokens: int = _FILE_DEFAULTS.get("segmentation_max_tokens", 3000)
    audiobooks_bucket: str = _FILE_DEFAULTS.get("audiobooks_bucket", "audiobooks")
    max_tts_chunk_chars: int = _FILE_DEFAULTS.get("max_chunk_chars", 4000)
    front_matter_min_pages: int = _FILE_DEFAULTS.get("front_matter_min_pages", 15)
    front_matter_max_pages: int = _FILE_DEFAULTS.get("front_matter_max_pages", 25)
    # Full-book pipeline: pages are packed into token-budgeted windows of at
    # most this many pages, so books of any length are covered (no page cap).
    extraction_batch_pages: int = _FILE_DEFAULTS.get("batch_pages", 25)
    # Input budget per segmentation request: windows are sized to fit, so
    # oversized text never exceeds the model's token limit.
    segmentation_token_limit: int = _FILE_DEFAULTS.get("token_limit", 3000)
    segmentation_chars_per_token: float = _FILE_DEFAULTS.get("chars_per_token", 4.0)
    # "stdlib" or "langchain" (langchain-text-splitters, installed separately).
    segmentation_text_splitter: str = _FILE_DEFAULTS.get("text_splitter", "stdlib")
    segmentation_text_splitter_overlap_chars: int = _FILE_DEFAULTS.get("text_splitter_overlap", 0)
    segmentation_max_retries: int = _FILE_DEFAULTS.get("max_retries", 1)
    # Parallel TTS: one worker per chapter, each chapter's chunks also
    # synthesized concurrently.
    tts_max_concurrency: int = _FILE_DEFAULTS.get("max_concurrency", 4)
    tts_chunk_concurrency: int = _FILE_DEFAULTS.get("chunk_concurrency", 5)


settings = Settings()
