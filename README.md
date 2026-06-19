# Telegram Chat AI Summary Bot

A Telegram bot that records chat messages while it is running and summarizes only the messages after the previous successful `/summary`. Summaries run through a local Ollama model by default, or a hosted provider such as OpenRouter for deployment.

## Important Telegram Limitations

Telegram bots cannot fetch arbitrary old group history. This bot can summarize messages it has received since it was added and running.

For group chats, disable BotFather privacy mode so the bot receives normal group messages:

1. Open BotFather.
2. Run `/setprivacy`.
3. Choose your bot.
4. Select `Disable`.
5. Remove and re-add the bot to the group if messages are still not arriving.

## Setup

```bash
cd ~/Documents/telegram-chat-ai-summary
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```bash
TELEGRAM_BOT_TOKEN=your-new-botfather-token
```

Keep `.env` local. Do not commit it.

## Summary Instructions

The bot can load extra persona and group context from `context/instructions.md`.
The default `.env.example` enables it with:

```bash
SUMMARY_INSTRUCTIONS_PATH=context/instructions.md
```

Edit that file to describe how AkiKai should summarize this group. Keep stable guidance there, such as the bot persona, the group's purpose, recurring project names, or preferred summary style. The bot will still only summarize messages it has actually received.

## Ollama Setup

For local development, install Ollama, start it, and pull a model:

```bash
ollama serve
ollama pull qwen3:latest
```

The default `.env.example` uses:

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:latest
```

Ollama currently maps `qwen3:latest` to the 8B Qwen3 model. For higher quality on a machine with enough memory, pull and set `OLLAMA_MODEL=qwen3:30b` instead. `qwen3:235b` is also available, but it is a very large model and is not practical on most laptops.

## OpenRouter Setup

For hosted Qwen without running Ollama locally, set:

```bash
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=your-openrouter-api-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/free
```

`OPENROUTER_API_KEY` is preferred. `QWEN_API_KEY` is also accepted for compatibility with older local `.env` files.

You can switch to any other OpenRouter chat model by changing only `OPENROUTER_MODEL`.
To try multiple fallbacks before returning an error, set `OPENROUTER_MODELS` as a comma-separated list. The bot tries up to `MODEL_MAX_ATTEMPTS`, capped at 5:

```bash
OPENROUTER_MODELS=openrouter/free,meta-llama/llama-3.2-3b-instruct:free,qwen/qwen3-coder:free
MODEL_MAX_ATTEMPTS=5
```

If only one model is configured, the bot can retry that same model/router up to `MODEL_MAX_ATTEMPTS` times. This is useful with `openrouter/free`, because OpenRouter may route each attempt to a different free backend.

## Render Free Deployment

Render Free cannot run local Ollama, and its filesystem is temporary. For a free cloud deployment, use:

- Render Free Web Service for the Telegram webhook
- Neon Free Postgres for message and summary storage
- OpenRouter for hosted Qwen summaries

Steps:

1. Rotate your Telegram bot token in BotFather before deploying.
2. Push this repo to GitHub.
3. Create a free Neon Postgres project and copy its pooled connection string.
4. Create an OpenRouter API key.
5. In Render, create a new Blueprint from this repo's `render.yaml`.
6. Set these Render environment variables:

```bash
TELEGRAM_BOT_TOKEN=your-rotated-bot-token
DATABASE_URL=your-neon-pooled-postgres-url
OPENROUTER_API_KEY=your-openrouter-api-key
WEBHOOK_URL=https://your-render-service-name.onrender.com
```

The blueprint sets these defaults:

```bash
APP_MODE=webhook
MODEL_PROVIDER=openrouter
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/free
OPENROUTER_MODELS=openrouter/free,meta-llama/llama-3.2-3b-instruct:free,qwen/qwen3-coder:free
MODEL_MAX_ATTEMPTS=5
SUMMARY_INSTRUCTIONS_PATH=context/instructions.md
```

Render Free web services spin down after idle time, so the first message after inactivity can be delayed while the service wakes up.

## Run

```bash
source .venv/bin/activate
python -m summary_bot
```

## Commands

- `/summary` summarizes messages since the previous successful summary.
- `/lastsummary` shows the last saved summary for the current chat.
- `/stats` shows stored and unsummarized message counts.
- `/reset_summary` moves the checkpoint to the latest stored message without calling the model.
- `/help` shows usage inside Telegram.

## How Checkpointing Works

The bot stores incoming messages in SQLite. When `/summary` succeeds, it saves the summary and advances the chat checkpoint to the latest message included in that summary. If the Ollama request fails, the checkpoint is not advanced, so the next `/summary` will retry the same interval.
