from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - runtime dependency loaded via requirements
    def load_dotenv(*args, **kwargs):  # type: ignore[override]
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_json(value: str) -> Dict[str, object]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("OPENWEBUI_FEATURES_JSON must decode to a JSON object")
    return parsed


@dataclass(frozen=True)
class BotConfig:
    base_url: str
    bot_token: str
    bot_session_token: str
    bot_email: str
    bot_password: str
    bot_user_id: str
    bot_display_name: str
    model_id: str
    terminal_id: str
    skill_ids: List[str]
    tool_ids: List[str]
    tool_server_ids: List[str]
    features: Dict[str, object]
    force_native_function_calling: bool
    channel_context_limit: int
    thread_context_limit: int
    completion_timeout_seconds: int
    tool_timeout_seconds: int
    startup_retry_seconds: int
    state_db_path: Path
    log_level: str
    socketio_debug: bool
    log_raw_channel_events: bool
    log_message_content: bool

    @classmethod
    def from_env(cls) -> "BotConfig":
        base_url = os.getenv("OPENWEBUI_BASE_URL", "").rstrip("/")
        bot_token = os.getenv("OPENWEBUI_BOT_TOKEN", "")
        bot_session_token = os.getenv("OPENWEBUI_BOT_SESSION_TOKEN", "")
        bot_email = os.getenv("OPENWEBUI_BOT_EMAIL", "")
        bot_password = os.getenv("OPENWEBUI_BOT_PASSWORD", "")
        bot_user_id = os.getenv("OPENWEBUI_BOT_USER_ID", "")

        missing = [
            key
            for key, value in {
                "OPENWEBUI_BASE_URL": base_url,
                "OPENWEBUI_BOT_TOKEN": bot_token,
                "OPENWEBUI_BOT_USER_ID": bot_user_id,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError("Missing required environment variables: " + ", ".join(missing))

        return cls(
            base_url=base_url,
            bot_token=bot_token,
            bot_session_token=bot_session_token,
            bot_email=bot_email,
            bot_password=bot_password,
            bot_user_id=bot_user_id,
            bot_display_name=os.getenv("OPENWEBUI_BOT_DISPLAY_NAME", "TEAM-BOT"),
            model_id=os.getenv("OPENWEBUI_MODEL_ID", "gpt-5-mini"),
            terminal_id=os.getenv("OPENWEBUI_TERMINAL_ID", "").strip(),
            skill_ids=_split_csv(os.getenv("OPENWEBUI_SKILL_IDS", "")),
            tool_ids=_split_csv(os.getenv("OPENWEBUI_TOOL_IDS", "")),
            tool_server_ids=_split_csv(os.getenv("OPENWEBUI_TOOL_SERVER_IDS", "")),
            features=_parse_json(os.getenv("OPENWEBUI_FEATURES_JSON", "")),
            force_native_function_calling=_parse_bool(
                os.getenv("OPENWEBUI_FORCE_NATIVE_FUNCTION_CALLING", "")
            ),
            channel_context_limit=int(os.getenv("CHANNEL_CONTEXT_LIMIT", "20")),
            thread_context_limit=int(os.getenv("THREAD_CONTEXT_LIMIT", "50")),
            completion_timeout_seconds=int(os.getenv("COMPLETION_TIMEOUT_SECONDS", "60")),
            tool_timeout_seconds=int(os.getenv("OPENWEBUI_TOOL_TIMEOUT_SECONDS", "300")),
            startup_retry_seconds=int(os.getenv("OPENWEBUI_STARTUP_RETRY_SECONDS", "5")),
            state_db_path=Path(os.getenv("STATE_DB_PATH", "/tmp/team-bot-state.db")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            socketio_debug=_parse_bool(os.getenv("SOCKETIO_DEBUG", "")),
            log_raw_channel_events=_parse_bool(os.getenv("LOG_RAW_CHANNEL_EVENTS", "")),
            log_message_content=_parse_bool(os.getenv("LOG_MESSAGE_CONTENT", "")),
        )
