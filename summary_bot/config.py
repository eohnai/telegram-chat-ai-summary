from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    app_mode: str
    webhook_url: str | None
    webhook_secret_token: str | None
    model_provider: str
    model_base_url: str
    model_name: str
    model_api_key: str | None
    model_timeout_seconds: float
    model_temperature: float
    database_url: str | None
    database_path: Path
    summary_language: str
    summary_instructions: str | None
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


def _env_float_alias(name: str, fallback_name: str, default: float) -> float:
    if os.getenv(name) is not None:
        return _env_float(name, default)
    return _env_float(fallback_name, default)


def _env_file_text(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    path = Path(raw_value).expanduser()
    if not path.exists():
        raise RuntimeError(f"{name} points to a file that does not exist: {path}")
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    database_path = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")).expanduser()
    model_provider = os.getenv("MODEL_PROVIDER", "").strip().lower() or "ollama"
    if model_provider not in {"ollama", "gemini", "openrouter"}:
        raise RuntimeError("MODEL_PROVIDER must be 'ollama', 'gemini', or 'openrouter'")

    if model_provider == "ollama":
        model_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        model_name = os.getenv("OLLAMA_MODEL", "qwen3:latest").strip()
        model_api_key = None
    elif model_provider == "gemini":
        model_base_url = os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ).strip()
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
        model_api_key = os.getenv("GEMINI_API_KEY", "").strip() or None
        if not model_api_key:
            raise RuntimeError("GEMINI_API_KEY is required when MODEL_PROVIDER=gemini")
    else:
        model_base_url = os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1",
        ).strip()
        model_name = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-next-80b-a3b-instruct:free").strip()
        model_api_key = (
            os.getenv("OPENROUTER_API_KEY", "").strip()
            or os.getenv("QWEN_API_KEY", "").strip()
            or None
        )
        if not model_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY or QWEN_API_KEY is required when MODEL_PROVIDER=openrouter"
            )

    return Settings(
        telegram_bot_token=telegram_bot_token,
        app_mode=os.getenv("APP_MODE", "polling").strip().lower() or "polling",
        webhook_url=os.getenv("WEBHOOK_URL", "").strip() or None,
        webhook_secret_token=os.getenv("WEBHOOK_SECRET_TOKEN", "").strip() or None,
        model_provider=model_provider,
        model_base_url=model_base_url or "http://localhost:11434",
        model_name=model_name or "qwen3:latest",
        model_api_key=model_api_key,
        model_timeout_seconds=_env_float_alias(
            "MODEL_TIMEOUT_SECONDS",
            "OLLAMA_TIMEOUT_SECONDS",
            300.0,
        ),
        model_temperature=_env_float_alias("MODEL_TEMPERATURE", "OLLAMA_TEMPERATURE", 0.2),
        database_url=os.getenv("DATABASE_URL", "").strip() or None,
        database_path=database_path,
        summary_language=os.getenv("SUMMARY_LANGUAGE", "same language as the chat").strip()
        or "same language as the chat",
        summary_instructions=_env_file_text("SUMMARY_INSTRUCTIONS_PATH"),
        max_transcript_chars=_env_int("MAX_TRANSCRIPT_CHARS", 120000),
        max_messages_per_summary=_env_int("MAX_MESSAGES_PER_SUMMARY", 0),
    )
