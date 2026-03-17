import tempfile
import unittest
from pathlib import Path

from team_bot.state import SQLiteStateStore


class StateStoreTests(unittest.TestCase):
    def test_claim_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStateStore(Path(tmpdir) / "state.db")
            self.assertTrue(store.claim("event-1"))
            self.assertFalse(store.claim("event-1"))


if __name__ == "__main__":
    unittest.main()
