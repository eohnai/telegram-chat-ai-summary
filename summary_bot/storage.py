from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class StoredMessage:
    chat_id: int
    message_id: int
    author: str
    text: str
    created_at: str


@dataclass(frozen=True)
class StoredSummary:
    chat_id: int
    from_message_id: int
    to_message_id: int
    summary: str
    message_count: int
    created_at: str


class ChatStore:
    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self._lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    author TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS chat_state (
                    chat_id INTEGER PRIMARY KEY,
                    last_summary_message_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    from_message_id INTEGER NOT NULL,
                    to_message_id INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_message(
        self,
        *,
        chat_id: int,
        message_id: int,
        author: str,
        text: str,
        created_at: datetime,
    ) -> None:
        timestamp = _format_datetime(created_at)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO messages
                    (chat_id, message_id, author, text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, message_id, author, text, timestamp),
            )

    def get_checkpoint(self, chat_id: int) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT last_summary_message_id FROM chat_state WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return int(row["last_summary_message_id"]) if row else 0

    def get_latest_message_id(self, chat_id: int) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT MAX(message_id) AS latest_message_id FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return int(row["latest_message_id"]) if row and row["latest_message_id"] is not None else 0

    def get_new_messages(self, chat_id: int, limit: int | None = None) -> list[StoredMessage]:
        checkpoint = self.get_checkpoint(chat_id)
        query = """
            SELECT chat_id, message_id, author, text, created_at
            FROM messages
            WHERE chat_id = ? AND message_id > ?
            ORDER BY message_id ASC
        """
        params: tuple[int, ...] = (chat_id, checkpoint)
        if limit is not None and limit > 0:
            query += " LIMIT ?"
            params = (chat_id, checkpoint, limit)

        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_message_from_row(row) for row in rows]

    def count_new_messages(self, chat_id: int) -> int:
        checkpoint = self.get_checkpoint(chat_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM messages
                WHERE chat_id = ? AND message_id > ?
                """,
                (chat_id, checkpoint),
            ).fetchone()
        return int(row["count"])

    def count_messages(self, chat_id: int) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return int(row["count"])

    def save_summary(
        self,
        *,
        chat_id: int,
        from_message_id: int,
        to_message_id: int,
        summary: str,
        message_count: int,
    ) -> None:
        now = _format_datetime(datetime.now(timezone.utc))
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO summaries
                    (chat_id, from_message_id, to_message_id, summary, message_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chat_id, from_message_id, to_message_id, summary, message_count, now),
            )
            self._set_checkpoint(connection, chat_id, to_message_id, now)

    def reset_checkpoint(self, chat_id: int, message_id: int) -> None:
        now = _format_datetime(datetime.now(timezone.utc))
        with self._lock, self._connect() as connection:
            self._set_checkpoint(connection, chat_id, message_id, now)

    def get_latest_summary(self, chat_id: int) -> StoredSummary | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT chat_id, from_message_id, to_message_id, summary, message_count, created_at
                FROM summaries
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
        return _summary_from_row(row) if row else None

    @staticmethod
    def _set_checkpoint(
        connection: sqlite3.Connection,
        chat_id: int,
        message_id: int,
        updated_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO chat_state (chat_id, last_summary_message_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                last_summary_message_id = excluded.last_summary_message_id,
                updated_at = excluded.updated_at
            """,
            (chat_id, message_id, updated_at),
        )


def _message_from_row(row: sqlite3.Row) -> StoredMessage:
    return StoredMessage(
        chat_id=int(row["chat_id"]),
        message_id=int(row["message_id"]),
        author=str(row["author"]),
        text=str(row["text"]),
        created_at=str(row["created_at"]),
    )


def _summary_from_row(row: sqlite3.Row) -> StoredSummary:
    return StoredSummary(
        chat_id=int(row["chat_id"]),
        from_message_id=int(row["from_message_id"]),
        to_message_id=int(row["to_message_id"]),
        summary=str(row["summary"]),
        message_count=int(row["message_count"]),
        created_at=str(row["created_at"]),
    )


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")

