"""SQLite storage for group messages."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    ts_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat_ts ON messages (chat_id, ts_ms);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages (ts_ms);
"""


@dataclass(frozen=True)
class StoredMessage:
    user_id: str
    name: str
    text: str
    ts_ms: int


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class Store:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def add(self, chat_id: str, user_id: str, name: str, text: str, ts_ms: int) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO messages (chat_id, user_id, name, text, ts_ms) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, name, text, ts_ms),
            )

    def since(self, chat_id: str, since_ms: int, limit: int) -> tuple[list[StoredMessage], int]:
        """Return the most recent `limit` messages since `since_ms` (oldest first),
        plus the total number of messages in that window."""
        total = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND ts_ms >= ?",
            (chat_id, since_ms),
        ).fetchone()[0]
        rows = self._conn.execute(
            "SELECT user_id, name, text, ts_ms FROM messages WHERE chat_id = ? AND ts_ms >= ?"
            " ORDER BY ts_ms DESC, id DESC LIMIT ?",
            (chat_id, since_ms, limit),
        ).fetchall()
        return [StoredMessage(*row) for row in reversed(rows)], total

    def speakers(self, chat_id: str, since_ms: int) -> dict[str, str]:
        """Map user_id to their most recent display name, for everyone who spoke since `since_ms`."""
        rows = self._conn.execute(
            "SELECT user_id, name FROM messages WHERE chat_id = ? AND ts_ms >= ? AND user_id != ''"
            " ORDER BY ts_ms, id",
            (chat_id, since_ms),
        ).fetchall()
        return dict(rows)

    def delete_older_than(self, cutoff_ms: int) -> int:
        with self._conn:
            return self._conn.execute("DELETE FROM messages WHERE ts_ms < ?", (cutoff_ms,)).rowcount

    def delete_chat(self, chat_id: str) -> int:
        with self._conn:
            return self._conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,)).rowcount

    def close(self) -> None:
        self._conn.close()
