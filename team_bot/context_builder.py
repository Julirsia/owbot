from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


MENTION_PATTERN = re.compile(r"<@([A-Z]):([^|>]+)(?:\|([^>]+))?>")


def extract_mentions(message: str) -> List[Dict[str, str]]:
    return [
        {"id_type": id_type, "id": mention_id, "label": label or mention_id}
        for id_type, mention_id, label in MENTION_PATTERN.findall(message or "")
    ]


def replace_mentions(message: str, use_label: bool = True) -> str:
    def replacer(match: re.Match[str]) -> str:
        _id_type, mention_id, label = match.groups()
        if use_label and label:
            return label
        return mention_id

    return MENTION_PATTERN.sub(replacer, message or "")


def strip_bot_mention(message: str, bot_user_id: str) -> str:
    stripped = re.sub(
        rf"<@U:{re.escape(bot_user_id)}(?:\|[^>]+)?>",
        "",
        message or "",
    )
    return re.sub(r"\s+", " ", stripped).strip()


def message_mentions_bot(message: str, bot_user_id: str) -> bool:
    return any(
        mention["id_type"] == "U" and mention["id"] == bot_user_id
        for mention in extract_mentions(message)
    )


def _display_name(message: Dict[str, object]) -> str:
    meta = message.get("meta") or {}
    if isinstance(meta, dict) and meta.get("model_name"):
        return str(meta["model_name"])

    user = message.get("user") or {}
    if isinstance(user, dict) and user.get("name"):
        return str(user["name"])

    if message.get("user_id"):
        return str(message["user_id"])

    return "Unknown"


def _format_message(message: Dict[str, object]) -> str:
    content = replace_mentions(str(message.get("content") or ""))
    return f"{_display_name(message)}: {content}".strip()


@dataclass
class InvocationContext:
    channel_lines: List[str]
    thread_lines: List[str]
    prompt: str
    thread_root_id: Optional[str]


def build_invocation_context(
    invocation_message: Dict[str, object],
    recent_channel_messages: Iterable[Dict[str, object]],
    thread_root_message: Optional[Dict[str, object]],
    thread_messages: Iterable[Dict[str, object]],
    bot_user_id: str,
) -> InvocationContext:
    invocation_created_at = int(invocation_message.get("created_at") or 0)

    filtered_channel_messages = [
        message
        for message in recent_channel_messages
        if int(message.get("created_at") or 0) <= invocation_created_at
    ]
    filtered_channel_messages.sort(key=lambda message: int(message.get("created_at") or 0))

    channel_lines = [_format_message(message) for message in filtered_channel_messages]

    thread_root_id = None
    thread_lines: List[str] = []
    if thread_root_message:
        thread_root_id = str(thread_root_message.get("id"))
        thread_items = [thread_root_message, *thread_messages]
        thread_items.sort(key=lambda message: int(message.get("created_at") or 0))
        thread_lines = [_format_message(message) for message in thread_items]

    current_request = replace_mentions(
        strip_bot_mention(str(invocation_message.get("content") or ""), bot_user_id)
    )
    if not current_request:
        current_request = "최근 대화를 바탕으로 사용자의 의도를 해석하고 필요한 응답을 제공하세요."

    prompt_parts = [
        "채널 최근 대화:",
        "\n".join(channel_lines) if channel_lines else "(없음)",
    ]

    if thread_lines:
        prompt_parts.extend(
            [
                "",
                "현재 스레드 대화:",
                "\n".join(thread_lines),
            ]
        )

    prompt_parts.extend(
        [
            "",
            "현재 호출 메시지:",
            _format_message(invocation_message),
            "",
            "사용자 요청:",
            current_request,
        ]
    )

    return InvocationContext(
        channel_lines=channel_lines,
        thread_lines=thread_lines,
        prompt="\n".join(prompt_parts).strip(),
        thread_root_id=thread_root_id,
    )


SYSTEM_PROMPT = (
    "너는 Open WebUI 채널에서 호출되는 TEAM-BOT이다. "
    "반드시 한국어로 답하고, 제공된 채널 문맥과 현재 스레드 문맥만 우선 사용한다. "
    "문맥에 없는 사실은 추정하지 말고, 불충분하면 짧게 확인 질문을 한다. "
    "도구가 필요할 때만 Open WebUI에 연결된 도구를 사용하고, 수행 불가한 요청은 이유를 짧게 설명한다."
)
