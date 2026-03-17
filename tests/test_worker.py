import asyncio
import tempfile
import unittest
from pathlib import Path

from team_bot.config import BotConfig
from team_bot.worker import PendingCompletion, TeamBotWorker


def make_config(*, terminal_id: str = "") -> BotConfig:
    temp_dir = tempfile.mkdtemp(prefix="owbot-tests-")
    return BotConfig(
        base_url="http://example.test",
        bot_token="token",
        bot_session_token="",
        bot_email="",
        bot_password="",
        bot_user_id="bot-user-id",
        bot_display_name="bot",
        model_id="test-model",
        terminal_id=terminal_id,
        skill_ids=[],
        tool_ids=[],
        tool_server_ids=[],
        features={},
        channel_context_limit=20,
        thread_context_limit=50,
        completion_timeout_seconds=30,
        tool_timeout_seconds=60,
        state_db_path=Path(temp_dir) / "state.db",
        log_level="INFO",
        socketio_debug=False,
        log_raw_channel_events=False,
        log_message_content=False,
    )


class TeamBotWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_startup_checks_enables_native_tool_mode_from_model_preset(self) -> None:
        worker = TeamBotWorker(make_config())

        class DummyClient:
            async def get_model(self, model_id: str):
                return {
                    "id": model_id,
                    "params": {"function_calling": "native"},
                    "meta": {"builtinTools": {"knowledge": True}, "skillIds": []},
                }

            async def probe_terminal_connection(self, terminal_id: str):
                raise AssertionError("terminal probe should not be called")

        worker.client = DummyClient()  # type: ignore[assignment]

        await worker._run_startup_checks()

        self.assertTrue(worker._model_uses_native_tools)
        self.assertTrue(worker._uses_native_tools())

    async def test_run_startup_checks_probes_terminal_when_configured(self) -> None:
        worker = TeamBotWorker(make_config(terminal_id="terminal-1"))
        observed_terminal_ids = []

        class DummyClient:
            async def get_model(self, model_id: str):
                return {"id": model_id, "params": {}, "meta": {}}

            async def probe_terminal_connection(self, terminal_id: str):
                observed_terminal_ids.append(terminal_id)
                return {"cwd": {"path": "/tmp"}, "ports": []}

        worker.client = DummyClient()  # type: ignore[assignment]

        await worker._run_startup_checks()

        self.assertEqual(observed_terminal_ids, ["terminal-1"])

    async def test_fail_pending_completions_sets_exception_on_all_futures(self) -> None:
        worker = TeamBotWorker(make_config())
        future = asyncio.get_running_loop().create_future()
        error = RuntimeError("socket disconnected")
        worker._pending_completions[("chat", "message")] = PendingCompletion(future=future)

        worker._fail_pending_completions(error)

        self.assertTrue(future.done())
        self.assertIs(future.exception(), error)


if __name__ == "__main__":
    unittest.main()
