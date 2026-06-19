from __future__ import annotations

import unittest

from summary_bot.summarizer import (
    OpenRouterChatSummarizer,
    _instructions,
    _looks_like_non_summary,
    _strip_thinking_blocks,
)


class SummarizerTest(unittest.TestCase):
    def test_strip_thinking_blocks_removes_qwen_reasoning(self) -> None:
        content = "<think>\nInternal reasoning\n</think>\n\nMain topics\n- Lunch plans"

        self.assertEqual(_strip_thinking_blocks(content).strip(), "Main topics\n- Lunch plans")

    def test_strip_thinking_blocks_removes_plain_qwen_reasoning(self) -> None:
        content = "Thinking...\nInternal reasoning\n...done thinking.\n\nMain topics\n- Lunch plans"

        self.assertEqual(_strip_thinking_blocks(content).strip(), "Main topics\n- Lunch plans")

    def test_instructions_include_group_specific_context(self) -> None:
        instructions = _instructions(
            "English",
            "You are AkiKai, a chat summary helper.",
        )

        self.assertIn("Write in English.", instructions)
        self.assertIn("Group-specific instructions:", instructions)
        self.assertIn("You are AkiKai, a chat summary helper.", instructions)

    def test_safety_label_is_not_a_valid_summary(self) -> None:
        self.assertTrue(_looks_like_non_summary("User Safety: safe"))

    def test_low_signal_summary_is_valid(self) -> None:
        self.assertFalse(
            _looks_like_non_summary(
                "This transcript contains only casual, low-signal messages with no "
                "substantive content to summarize."
            )
        )

    def test_openrouter_model_attempts_are_capped_at_five(self) -> None:
        summarizer = OpenRouterChatSummarizer(
            base_url="https://openrouter.ai/api/v1",
            api_key="test",
            model="openrouter/free",
            models=("m1", "m2", "m3", "m4", "m5", "m6"),
            max_attempts=10,
            timeout_seconds=1,
            temperature=0.2,
            max_transcript_chars=1000,
            summary_language="English",
        )

        self.assertEqual(summarizer._model_attempts(), ("m1", "m2", "m3", "m4", "m5"))

    def test_single_openrouter_model_can_retry_same_router(self) -> None:
        summarizer = OpenRouterChatSummarizer(
            base_url="https://openrouter.ai/api/v1",
            api_key="test",
            model="openrouter/free",
            models=("openrouter/free",),
            max_attempts=3,
            timeout_seconds=1,
            temperature=0.2,
            max_transcript_chars=1000,
            summary_language="English",
        )

        self.assertEqual(
            summarizer._model_attempts(),
            ("openrouter/free", "openrouter/free", "openrouter/free"),
        )


if __name__ == "__main__":
    unittest.main()
