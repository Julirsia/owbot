import tempfile
import unittest
from pathlib import Path

from team_bot.state import SQLiteStateStore


class SQLiteStateStoreTests(unittest.TestCase):
    def test_claim_runs_cleanup_when_interval_elapsed(self) -> None:
        temp_dir = tempfile.mkdtemp(prefix="owbot-state-tests-")
        clock = {"now": 1_000}

        def now_fn() -> float:
            return float(clock["now"])

        store = SQLiteStateStore(
            Path(temp_dir) / "state.db",
            retention_seconds=10,
            cleanup_interval_seconds=5,
            now_fn=now_fn,
        )

        self.assertTrue(store.claim("fresh"))

        clock["now"] = 1_001
        with store._connect() as connection:
            connection.execute(
                "INSERT INTO processed_events (dedupe_key, processed_at) VALUES (?, ?)",
                ("expired", 980),
            )

        clock["now"] = 1_007
        self.assertTrue(store.claim("next"))

        with store._connect() as connection:
            remaining = {
                row[0]
                for row in connection.execute("SELECT dedupe_key FROM processed_events").fetchall()
            }

        self.assertNotIn("expired", remaining)
        self.assertIn("fresh", remaining)
        self.assertIn("next", remaining)

    def test_cleanup_expired_can_be_forced(self) -> None:
        temp_dir = tempfile.mkdtemp(prefix="owbot-state-tests-")
        clock = {"now": 2_000}

        def now_fn() -> float:
            return float(clock["now"])

        store = SQLiteStateStore(
            Path(temp_dir) / "state.db",
            retention_seconds=10,
            cleanup_interval_seconds=1000,
            now_fn=now_fn,
        )

        with store._connect() as connection:
            connection.execute(
                "INSERT INTO processed_events (dedupe_key, processed_at) VALUES (?, ?)",
                ("expired", 1_980),
            )

        deleted = store.cleanup_expired(force=True)
        self.assertEqual(deleted, 1)


if __name__ == "__main__":
    unittest.main()
