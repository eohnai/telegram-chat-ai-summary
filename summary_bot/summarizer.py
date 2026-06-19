from __future__ import annotations

from collections.abc import Iterable
import re

import httpx

from .storage import StoredMessage


class ConfigurationError(RuntimeError):
    """Raised when the summarizer is missing required runtime configuration."""


class BaseChatSummarizer:
    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float,
        temperature: float,
        max_transcript_chars: int,
        summary_language: str,
        summary_instructions: str | None = None,
    ):
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_transcript_chars = max(max_transcript_chars, 1000)
        self.summary_language = summary_language
        self.summary_instructions = summary_instructions

    async def summarize(
        self,
        messages: list[StoredMessage],
        *,
        previous_summary: str | None = None,
    ) -> str:
        if not messages:
            return "No new messages to summarize."

        chunks = list(_chunk_messages(messages, self.max_transcript_chars))
        if len(chunks) == 1:
            return await self._summarize_chunk(
                chunk=chunks[0],
                previous_summary=previous_summary,
                chunk_label=None,
            )

        partial_summaries = []
        for index, chunk in enumerate(chunks, start=1):
            partial_summaries.append(
                await self._summarize_chunk(
                    chunk=chunk,
                    previous_summary=previous_summary if index == 1 else None,
                    chunk_label=f"{index}/{len(chunks)}",
                )
            )

        return await self._combine_summaries(partial_summaries, previous_summary=previous_summary)

    async def _summarize_chunk(
        self,
        *,
        chunk: list[StoredMessage],
        previous_summary: str | None,
        chunk_label: str | None,
    ) -> str:
        transcript = _format_transcript(chunk)
        scope = "the new transcript"
        if chunk_label:
            scope = f"chunk {chunk_label} of the new transcript"

        user_content = (
            f"Previous summary for context only:\n{previous_summary or '(none)'}\n\n"
            f"Summarize {scope}. Cover only messages in this transcript.\n\n"
            f"Transcript:\n{transcript}"
        )

        return await self._create_response(user_content)

    async def _combine_summaries(
        self,
        partial_summaries: list[str],
        *,
        previous_summary: str | None,
    ) -> str:
        content = "\n\n".join(
            f"Chunk summary {index}:\n{summary}"
            for index, summary in enumerate(partial_summaries, start=1)
        )
        user_content = (
            f"Previous summary for context only:\n{previous_summary or '(none)'}\n\n"
            "Combine these chunk summaries into one incremental Telegram chat summary. "
            "Avoid repeating the previous summary except where it clarifies new follow-ups.\n\n"
            f"{content}"
        )
        return await self._create_response(user_content)

    async def _create_response(self, user_content: str) -> str:
        raise NotImplementedError

    def _messages(self, user_content: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": _instructions(
                    self.summary_language,
                    self.summary_instructions,
                ),
            },
            {"role": "user", "content": user_content},
        ]


class OllamaChatSummarizer(BaseChatSummarizer):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        temperature: float,
        max_transcript_chars: int,
        summary_language: str,
        summary_instructions: str | None = None,
    ):
        super().__init__(
            model=model,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_transcript_chars=max_transcript_chars,
            summary_language=summary_language,
            summary_instructions=summary_instructions,
        )
        self.base_url = base_url.rstrip("/")

    async def _create_response(self, user_content: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": self._messages(user_content),
            "options": {"temperature": self.temperature},
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                trust_env=False,
            ) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise ConfigurationError(
                f"Cannot connect to Ollama at {self.base_url}. Start Ollama and run "
                f"`ollama pull {self.model}` before using /summary."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = _error_detail(exc.response)
            raise RuntimeError(f"Ollama request failed: {detail}") from exc

        data = response.json()
        content = (data.get("message") or {}).get("content") or data.get("response")
        if not content:
            raise RuntimeError("Ollama returned no summary text")
        return _strip_thinking_blocks(str(content)).strip()


class OpenAICompatibleChatSummarizer(BaseChatSummarizer):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider_name: str,
        extra_headers: dict[str, str] | None = None,
        timeout_seconds: float,
        temperature: float,
        max_transcript_chars: int,
        summary_language: str,
        summary_instructions: str | None = None,
    ):
        super().__init__(
            model=model,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_transcript_chars=max_transcript_chars,
            summary_language=summary_language,
            summary_instructions=summary_instructions,
        )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_name = provider_name
        self.extra_headers = extra_headers or {}

    async def _create_response(self, user_content: str) -> str:
        payload = {
            "model": self.model,
            "messages": self._messages(user_content),
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            **self.extra_headers,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                trust_env=False,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise ConfigurationError(
                f"Cannot connect to {self.provider_name} API at {self.base_url}."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = _error_detail(exc.response)
            if exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After")
                retry_hint = f" Try again in about {retry_after} seconds." if retry_after else ""
                raise ConfigurationError(
                    f"{self.provider_name} is temporarily rate-limited.{retry_hint}"
                ) from exc
            raise RuntimeError(f"{self.provider_name} API request failed: {detail}") from exc

        data = response.json()
        choices = data.get("choices") or []
        content = None
        if choices:
            content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError(f"{self.provider_name} API returned no summary text")
        return _strip_thinking_blocks(str(content)).strip()


class GeminiChatSummarizer(OpenAICompatibleChatSummarizer):
    def __init__(self, **kwargs):
        super().__init__(provider_name="Gemini", **kwargs)


class OpenRouterChatSummarizer(OpenAICompatibleChatSummarizer):
    def __init__(self, **kwargs):
        super().__init__(
            provider_name="OpenRouter",
            extra_headers={
                "HTTP-Referer": "https://github.com/ianhoe/telegram-chat-ai-summary",
                "X-Title": "Telegram Chat AI Summary",
            },
            **kwargs,
        )


def _instructions(summary_language: str, summary_instructions: str | None = None) -> str:
    base_instructions = f"""
/no_think

You summarize Telegram group chats for people who need to catch up quickly.
Write in {summary_language}.

Return a concise but useful summary with these sections when relevant:
- Main topics
- Decisions
- Action items
- Open questions
- Notable links or files

Rules:
- Summarize only the new transcript provided by the user.
- Use the previous summary only as context for references and follow-ups.
- Keep names, dates, amounts, links, and commitments precise.
- Do not invent owners, decisions, or action items.
- Return only the final summary. Do not include hidden reasoning or thinking tags.
- If the chat is mostly casual or low-signal, say that briefly.
""".strip()
    if not summary_instructions:
        return base_instructions
    return f"{base_instructions}\n\nGroup-specific instructions:\n{summary_instructions.strip()}"


def _strip_thinking_blocks(content: str) -> str:
    without_tags = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(
        r"^\s*Thinking\.\.\..*?\.\.\.done thinking\.\s*",
        "",
        without_tags,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _chunk_messages(
    messages: Iterable[StoredMessage],
    max_chars: int,
) -> Iterable[list[StoredMessage]]:
    chunk: list[StoredMessage] = []
    chunk_chars = 0
    for message in messages:
        rendered = _format_message(message)
        rendered_length = len(rendered) + 1
        if chunk and chunk_chars + rendered_length > max_chars:
            yield chunk
            chunk = []
            chunk_chars = 0
        chunk.append(message)
        chunk_chars += rendered_length
    if chunk:
        yield chunk


def _format_transcript(messages: Iterable[StoredMessage]) -> str:
    return "\n".join(_format_message(message) for message in messages)


def _format_message(message: StoredMessage) -> str:
    text = " ".join(message.text.split())
    return f"[{message.created_at}] #{message.message_id} {message.author}: {text}"


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])
    return response.text
