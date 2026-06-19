from __future__ import annotations

import logging
import os

from telegram import BotCommand, Message, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings, load_settings
from .storage import MessageStore, build_store
from .summarizer import (
    BaseChatSummarizer,
    ConfigurationError,
    GeminiChatSummarizer,
    OllamaChatSummarizer,
    OpenRouterChatSummarizer,
)


LOGGER = logging.getLogger(__name__)
MAX_TELEGRAM_MESSAGE_LENGTH = 3900


def build_application(settings: Settings) -> Application:
    store = build_store(database_url=settings.database_url, database_path=settings.database_path)
    summarizer = _build_summarizer(settings)

    application = Application.builder().token(settings.telegram_bot_token).post_init(_set_bot_commands).build()

    application.bot_data["store"] = store
    application.bot_data["summarizer"] = summarizer
    application.bot_data["max_messages_per_summary"] = settings.max_messages_per_summary

    application.add_handler(CommandHandler(["start", "help"], help_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("lastsummary", last_summary_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("reset_summary", reset_summary_command))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, record_message))

    return application


def _build_summarizer(settings: Settings) -> BaseChatSummarizer:
    common_args = {
        "base_url": settings.model_base_url,
        "model": settings.model_name,
        "models": settings.model_names,
        "max_attempts": settings.model_max_attempts,
        "timeout_seconds": settings.model_timeout_seconds,
        "temperature": settings.model_temperature,
        "max_transcript_chars": settings.max_transcript_chars,
        "summary_language": settings.summary_language,
        "summary_instructions": settings.summary_instructions,
    }
    if settings.model_provider == "gemini":
        if settings.model_api_key is None:
            raise RuntimeError("GEMINI_API_KEY is required when MODEL_PROVIDER=gemini")
        return GeminiChatSummarizer(api_key=settings.model_api_key, **common_args)
    if settings.model_provider == "openrouter":
        if settings.model_api_key is None:
            raise RuntimeError("OPENROUTER_API_KEY is required when MODEL_PROVIDER=openrouter")
        return OpenRouterChatSummarizer(api_key=settings.model_api_key, **common_args)
    return OllamaChatSummarizer(**common_args)


async def _set_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("summary", "Summarize new messages"),
            BotCommand("lastsummary", "Show the latest saved summary"),
            BotCommand("stats", "Show stored and new message counts"),
            BotCommand("reset_summary", "Start the next summary from now"),
            BotCommand("help", "Show usage"),
        ]
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "I record messages while running and summarize new messages since the previous "
        "successful /summary.\n\n"
        "Commands:\n"
        "/summary - summarize new messages\n"
        "/lastsummary - show the latest saved summary\n"
        "/stats - show stored/new message counts\n"
        "/reset_summary - start the next summary from now"
    )


async def record_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    text = _message_text(message)
    if not text:
        return

    store: MessageStore = context.application.bot_data["store"]
    store.save_message(
        chat_id=chat.id,
        message_id=message.message_id,
        author=_author_name(message),
        text=text,
        created_at=message.date,
    )


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    store: MessageStore = context.application.bot_data["store"]
    max_messages = int(context.application.bot_data.get("max_messages_per_summary") or 0)
    total_new_messages = store.count_new_messages(chat.id)
    if total_new_messages == 0:
        await message.reply_text("No new stored messages since the previous summary.")
        return

    limit = max_messages if max_messages > 0 else None
    messages = store.get_new_messages(chat.id, limit=limit)
    partial = len(messages) < total_new_messages

    summarizer: BaseChatSummarizer = context.application.bot_data["summarizer"]
    previous = store.get_latest_summary(chat.id)

    await message.chat.send_action(ChatAction.TYPING)
    try:
        summary = await summarizer.summarize(
            messages,
            previous_summary=previous.summary if previous else None,
        )
    except ConfigurationError as exc:
        await _reply_long_text(message, str(exc))
        return
    except Exception:
        LOGGER.exception("Failed to generate summary")
        await message.reply_text("Summary failed. The checkpoint was not advanced, so you can retry.")
        return

    from_message_id = messages[0].message_id
    to_message_id = messages[-1].message_id
    store.save_summary(
        chat_id=chat.id,
        from_message_id=from_message_id,
        to_message_id=to_message_id,
        summary=summary,
        message_count=len(messages),
    )

    heading = f"Summary since previous summary ({len(messages)} messages"
    if partial:
        heading += f" of {total_new_messages}; run /summary again for the next batch"
    heading += "):"

    await _reply_long_text(message, f"{heading}\n\n{summary}")


async def last_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    store: MessageStore = context.application.bot_data["store"]
    summary = store.get_latest_summary(chat.id)
    if summary is None:
        await message.reply_text("No summary has been saved for this chat yet.")
        return

    await _reply_long_text(
        message,
        f"Last summary ({summary.message_count} messages, through #{summary.to_message_id}):\n\n"
        f"{summary.summary}",
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    store: MessageStore = context.application.bot_data["store"]
    total = store.count_messages(chat.id)
    new = store.count_new_messages(chat.id)
    checkpoint = store.get_checkpoint(chat.id)
    await message.reply_text(
        f"Stored messages: {total}\n"
        f"New messages since previous summary: {new}\n"
        f"Checkpoint message ID: {checkpoint}"
    )


async def reset_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    store: MessageStore = context.application.bot_data["store"]
    latest_message_id = store.get_latest_message_id(chat.id)
    store.reset_checkpoint(chat.id, latest_message_id)
    await message.reply_text(f"Summary checkpoint reset to message #{latest_message_id}.")


async def _reply_long_text(message: Message, text: str) -> None:
    for chunk in _split_text(text, MAX_TELEGRAM_MESSAGE_LENGTH):
        await message.reply_text(chunk)


def _split_text(text: str, max_length: int) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        split_at = remaining.rfind("\n", 0, max_length)
        if split_at < max_length // 2:
            split_at = remaining.rfind(" ", 0, max_length)
        if split_at < max_length // 2:
            split_at = max_length
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _message_text(message: Message) -> str | None:
    text = message.text or message.caption
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def _author_name(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "Unknown"

    display_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    if user.username and display_name:
        return f"{display_name} (@{user.username})"
    if user.username:
        return f"@{user.username}"
    if display_name:
        return display_name
    return str(user.id)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = load_settings()
    application = build_application(settings)
    if settings.app_mode == "webhook":
        if not settings.webhook_url:
            raise RuntimeError("WEBHOOK_URL is required when APP_MODE=webhook")
        port = int(os.getenv("PORT", "10000"))
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="telegram",
            webhook_url=f"{settings.webhook_url.rstrip('/')}/telegram",
            allowed_updates=Update.ALL_TYPES,
            secret_token=settings.webhook_secret_token,
        )
        return
    if settings.app_mode != "polling":
        raise RuntimeError("APP_MODE must be either 'polling' or 'webhook'")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
