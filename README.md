# Telegram Chat AI Summary Bot

A polling Telegram bot that records chat messages while it is running and summarizes only the messages after the previous successful `/summary`. Summaries run through a local Ollama model by default.

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

## Ollama Setup

Install Ollama, start it, and pull a model:

```bash
ollama serve
ollama pull qwen3:8b
```

The default `.env.example` uses:

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

You can change `OLLAMA_MODEL` to another local model, for example `qwen2.5:7b`, `llama3.2`, or any model you have pulled into Ollama.

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
