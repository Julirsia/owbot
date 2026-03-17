#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        headers: Dict[str, str] = {}
        data = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            raise RuntimeError(f"{method} {path} failed with {exc.code}: {raw}") from exc
        return json.loads(raw) if raw else None

    def signin(self, email: str, password: str) -> Dict[str, Any]:
        return self.request(
            "POST",
            "/api/v1/auths/signin",
            payload={"email": email, "password": password},
        )


def create_group_channel(
    client: ApiClient,
    *,
    bot_token: str,
    bot_user_id: str,
    test_user_id: str,
) -> str:
    created = client.request(
        "POST",
        "/api/v1/channels/create",
        token=bot_token,
        payload={
            "name": f"owbot-e2e-{bot_user_id[:8]}",
            "description": "owbot automated channel/thread validation",
            "type": "group",
            "is_private": False,
            "user_ids": [test_user_id],
        },
    )
    return str(created["id"])


def post_message(
    client: ApiClient,
    *,
    channel_id: str,
    token: str,
    content: str,
    reply_to_id: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"content": content}
    if reply_to_id:
        payload["reply_to_id"] = reply_to_id
    if parent_id:
        payload["parent_id"] = parent_id
    return client.request(
        "POST",
        f"/api/v1/channels/{channel_id}/messages/post",
        token=token,
        payload=payload,
    )


def get_channel_messages(client: ApiClient, *, channel_id: str, token: str) -> List[Dict[str, Any]]:
    return client.request(
        "GET",
        f"/api/v1/channels/{channel_id}/messages?skip=0&limit=50",
        token=token,
    )


def get_thread_messages(
    client: ApiClient,
    *,
    channel_id: str,
    root_id: str,
    token: str,
) -> List[Dict[str, Any]]:
    return client.request(
        "GET",
        f"/api/v1/channels/{channel_id}/messages/{root_id}/thread?skip=0&limit=50",
        token=token,
    )


def wait_for_reply(
    client: ApiClient,
    *,
    channel_id: str,
    token: str,
    bot_user_id: str,
    reply_to_id: str,
    parent_id: Optional[str],
    timeout_seconds: int,
) -> Dict[str, Any]:
    started = time.time()
    while time.time() - started < timeout_seconds:
        if parent_id:
            messages = get_thread_messages(
                client, channel_id=channel_id, root_id=parent_id, token=token
            )
        else:
            messages = get_channel_messages(client, channel_id=channel_id, token=token)
        for message in messages:
            user = message.get("user") or {}
            if str(user.get("id") or "") != bot_user_id:
                continue
            if str(message.get("reply_to_id") or "") != reply_to_id:
                continue
            if parent_id and str(message.get("parent_id") or "") != parent_id:
                continue
            if not parent_id and message.get("parent_id") is not None:
                continue
            return message
        time.sleep(2)
    raise RuntimeError(
        f"Timed out waiting for bot reply channel_id={channel_id} reply_to_id={reply_to_id}"
    )


def print_result(name: str, message: Dict[str, Any]) -> None:
    preview = str(message.get("content") or "").strip().replace("\n", " ")
    if len(preview) > 160:
        preview = preview[:157] + "..."
    print(f"[PASS] {name}: {preview}")


def assert_successful_reply(message: Dict[str, Any]) -> None:
    content = str(message.get("content") or "").strip()
    if not content:
        raise RuntimeError("Bot reply was empty")

    failure_prefixes = (
        "요청을 처리하지 못했습니다:",
        "응답을 생성하지 못했습니다.",
        "도구를 호출했지만 최종 텍스트 응답이 비어 있습니다.",
    )
    if any(content.startswith(prefix) for prefix in failure_prefixes):
        raise RuntimeError(f"Bot reply indicates failure: {content}")


def main() -> int:
    client = ApiClient(env("OPENWEBUI_BASE_URL"))

    bot_auth = client.signin(env("OPENWEBUI_BOT_EMAIL"), env("OPENWEBUI_BOT_PASSWORD"))
    test_auth = client.signin(env("OWBOT_TEST_USER_EMAIL"), env("OWBOT_TEST_USER_PASSWORD"))

    bot_user_id = env("OPENWEBUI_BOT_USER_ID")
    bot_display_name = os.getenv("OPENWEBUI_BOT_DISPLAY_NAME", "TEAM-BOT").strip() or "TEAM-BOT"
    channel_id = os.getenv("OWBOT_TEST_CHANNEL_ID", "").strip()
    if not channel_id:
        channel_id = create_group_channel(
            client,
            bot_token=str(bot_auth["token"]),
            bot_user_id=bot_user_id,
            test_user_id=str(test_auth["id"]),
        )
        print(f"[INFO] created temporary test channel: {channel_id}")

    mention = f"<@U:{bot_user_id}|{bot_display_name}>"
    timeout_seconds = int(os.getenv("OWBOT_E2E_TIMEOUT_SECONDS", "120"))

    top_tool = post_message(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        content=f"{mention} 사용 가능한 knowledge base를 알려줘.",
    )
    top_tool_reply = wait_for_reply(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        bot_user_id=bot_user_id,
        reply_to_id=str(top_tool["id"]),
        parent_id=None,
        timeout_seconds=timeout_seconds,
    )
    assert_successful_reply(top_tool_reply)
    print_result("top-level tool", top_tool_reply)

    top_terminal = post_message(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        content=f"{mention} 현재 작업 디렉터리와 파일 몇 개를 보여줘. 터미널을 사용해도 돼.",
    )
    top_terminal_reply = wait_for_reply(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        bot_user_id=bot_user_id,
        reply_to_id=str(top_terminal["id"]),
        parent_id=None,
        timeout_seconds=timeout_seconds,
    )
    assert_successful_reply(top_terminal_reply)
    print_result("top-level terminal", top_terminal_reply)

    thread_root_tool = post_message(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        content="thread tool validation root",
    )
    thread_tool = post_message(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        content=f"{mention} 이 스레드에서 사용 가능한 knowledge base를 알려줘.",
        reply_to_id=str(thread_root_tool["id"]),
        parent_id=str(thread_root_tool["id"]),
    )
    thread_tool_reply = wait_for_reply(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        bot_user_id=bot_user_id,
        reply_to_id=str(thread_tool["id"]),
        parent_id=str(thread_root_tool["id"]),
        timeout_seconds=timeout_seconds,
    )
    assert_successful_reply(thread_tool_reply)
    print_result("thread tool", thread_tool_reply)

    thread_root_terminal = post_message(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        content="thread terminal validation root",
    )
    thread_terminal = post_message(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        content=f"{mention} 이 스레드에서 터미널로 pwd 와 ls -1 을 실행해서 요약해줘.",
        reply_to_id=str(thread_root_terminal["id"]),
        parent_id=str(thread_root_terminal["id"]),
    )
    thread_terminal_reply = wait_for_reply(
        client,
        channel_id=channel_id,
        token=str(test_auth["token"]),
        bot_user_id=bot_user_id,
        reply_to_id=str(thread_terminal["id"]),
        parent_id=str(thread_root_terminal["id"]),
        timeout_seconds=timeout_seconds,
    )
    assert_successful_reply(thread_terminal_reply)
    print_result("thread terminal", thread_terminal_reply)

    print("[DONE] channel/thread tool and terminal scenarios verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise
