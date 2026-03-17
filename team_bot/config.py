from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


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
    bot_user_id: str
    bot_display_name: str
    model_id: str
    tool_ids: List[str]
    tool_server_ids: List[str]
    features: Dict[str, object]
    channel_context_limit: int
    thread_context_limit: int
    completion_timeout_seconds: int
    state_db_path: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        base_url = os.getenv("OPENWEBUI_BASE_URL", "").rstrip("/")
        bot_token = os.getenv("OPENWEBUI_BOT_TOKEN", "")
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
            bot_user_id=bot_user_id,
            bot_display_name=os.getenv("OPENWEBUI_BOT_DISPLAY_NAME", "TEAM-BOT"),
            model_id=os.getenv("OPENWEBUI_MODEL_ID", "gpt-5-mini"),
            tool_ids=_split_csv(os.getenv("OPENWEBUI_TOOL_IDS", "")),
            tool_server_ids=_split_csv(os.getenv("OPENWEBUI_TOOL_SERVER_IDS", "")),
            features=_parse_json(os.getenv("OPENWEBUI_FEATURES_JSON", "")),
            channel_context_limit=int(os.getenv("CHANNEL_CONTEXT_LIMIT", "20")),
            thread_context_limit=int(os.getenv("THREAD_CONTEXT_LIMIT", "50")),
            completion_timeout_seconds=int(os.getenv("COMPLETION_TIMEOUT_SECONDS", "60")),
            state_db_path=Path(os.getenv("STATE_DB_PATH", "/tmp/team-bot-state.db")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
