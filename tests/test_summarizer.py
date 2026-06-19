from __future__ import annotations

import unittest

from summary_bot.summarizer import _instructions, _strip_thinking_blocks


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


if __name__ == "__main__":
    unittest.main()
