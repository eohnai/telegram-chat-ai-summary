from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from summary_bot.storage import ChatStore


class ChatStoreTest(unittest.TestCase):
    def test_save_summary_advances_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ChatStore(Path(directory) / "bot.sqlite3")
            self._save_message(store, message_id=10, text="first")
            self._save_message(store, message_id=11, text="second")

            new_messages = store.get_new_messages(123)
            self.assertEqual([message.message_id for message in new_messages], [10, 11])

            store.save_summary(
                chat_id=123,
                from_message_id=10,
                to_message_id=11,
                summary="summary",
                message_count=2,
            )

            self.assertEqual(store.get_checkpoint(123), 11)
            self.assertEqual(store.get_new_messages(123), [])
            latest = store.get_latest_summary(123)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.summary, "summary")

    def test_reset_checkpoint_uses_latest_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ChatStore(Path(directory) / "bot.sqlite3")
            self._save_message(store, message_id=5, text="before")
            self._save_message(store, message_id=8, text="now")

            store.reset_checkpoint(123, store.get_latest_message_id(123))

            self.assertEqual(store.get_checkpoint(123), 8)
            self.assertEqual(store.count_new_messages(123), 0)

    @staticmethod
    def _save_message(store: ChatStore, *, message_id: int, text: str) -> None:
        store.save_message(
            chat_id=123,
            message_id=message_id,
            author="Alice",
            text=text,
            created_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()

