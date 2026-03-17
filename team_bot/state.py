from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable


class SQLiteStateStore:
    def __init__(
        self,
        db_path: Path,
        *,
        retention_seconds: int = 7 * 24 * 60 * 60,
        cleanup_interval_seconds: int = 60 * 60,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_seconds = max(0, retention_seconds)
        self.cleanup_interval_seconds = max(0, cleanup_interval_seconds)
        self._now_fn = now_fn
        self._lock = threading.Lock()
        self._last_cleanup_at = 0
        self._initialize()
        self.cleanup_expired(force=True)

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
        now = int(self._now_fn())
        with self._lock:
            self._cleanup_expired_locked(now, force=False)
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO processed_events (dedupe_key, processed_at)
                    VALUES (?, ?)
                    """,
                    (dedupe_key, now),
                )
                return cursor.rowcount == 1

    def cleanup_expired(self, *, force: bool = False) -> int:
        now = int(self._now_fn())
        with self._lock:
            return self._cleanup_expired_locked(now, force=force)

    def _cleanup_expired_locked(self, now: int, *, force: bool) -> int:
        if self.retention_seconds <= 0:
            return 0
        if (
            not force
            and self.cleanup_interval_seconds > 0
            and now - self._last_cleanup_at < self.cleanup_interval_seconds
        ):
            return 0

        cutoff = now - self.retention_seconds
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM processed_events
                WHERE processed_at < ?
                """,
                (cutoff,),
            )
            deleted = cursor.rowcount or 0
        self._last_cleanup_at = now
        return deleted
