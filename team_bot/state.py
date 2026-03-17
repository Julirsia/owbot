from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class SQLiteStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    dedupe_key TEXT PRIMARY KEY,
                    processed_at INTEGER NOT NULL
                )
                """
            )

    def claim(self, dedupe_key: str) -> bool:
        now = int(time.time())
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO processed_events (dedupe_key, processed_at)
                    VALUES (?, ?)
                    """,
                    (dedupe_key, now),
                )
                return cursor.rowcount == 1
