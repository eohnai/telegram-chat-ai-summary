from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    ollama_temperature: float
    database_path: Path
    summary_language: str
    max_transcript_chars: int
    max_messages_per_summary: int


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return value


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if value < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return value


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    database_path = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")).expanduser()

    return Settings(
        telegram_bot_token=telegram_bot_token,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        or "http://localhost:11434",
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b").strip() or "qwen3:8b",
        ollama_timeout_seconds=_env_float("OLLAMA_TIMEOUT_SECONDS", 300.0),
        ollama_temperature=_env_float("OLLAMA_TEMPERATURE", 0.2),
        database_path=database_path,
        summary_language=os.getenv("SUMMARY_LANGUAGE", "same language as the chat").strip()
        or "same language as the chat",
        max_transcript_chars=_env_int("MAX_TRANSCRIPT_CHARS", 120000),
        max_messages_per_summary=_env_int("MAX_MESSAGES_PER_SUMMARY", 0),
    )
