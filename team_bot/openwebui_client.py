from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover - runtime dependency loaded via requirements
    aiohttp = None  # type: ignore[assignment]


log = logging.getLogger(__name__)


class OpenWebUIClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: int) -> None:
        if aiohttp is None:
            raise RuntimeError("aiohttp is required to use OpenWebUIClient")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("OpenWebUIClient session is not initialized")
        return self._session

    async def __aenter__(self) -> "OpenWebUIClient":
        self._session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        async with self.session.request(method, url, json=json_body) as response:
            raw_text = await response.text()
            data: Any
            if not raw_text.strip():
                data = None
            else:
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    data = raw_text
            if response.status >= 400:
                raise RuntimeError(f"{method} {path} failed with {response.status}: {data}")
            return data

    async def get_channel_messages(self, channel_id: str, limit: int) -> List[Dict[str, Any]]:
        return await self._request(
            "GET",
            f"/api/v1/channels/{channel_id}/messages?skip=0&limit={limit}",
        )

    async def get_channels(self) -> List[Dict[str, Any]]:
        response = await self._request("GET", "/api/v1/channels/")
        if response is None:
            return []
        if not isinstance(response, list):
            raise RuntimeError(
                f"GET /api/v1/channels/ returned non-list response: {response!r}"
            )
        return response

    async def get_current_user(self) -> Dict[str, Any]:
        response = await self._request("GET", "/api/v1/auths/")
        if not isinstance(response, dict):
            raise RuntimeError(f"GET /api/v1/auths/ returned non-dict response: {response!r}")
        return response

    async def sign_in(self, email: str, password: str) -> str:
        response = await self._request(
            "POST",
            "/api/v1/auths/signin",
            json_body={"email": email, "password": password},
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"POST /api/v1/auths/signin returned non-dict response: {response!r}")
        token = response.get("token")
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError(f"POST /api/v1/auths/signin returned no token: {response!r}")
        return token.strip()

    async def get_channel_message(self, channel_id: str, message_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/v1/channels/{channel_id}/messages/{message_id}")

    async def get_thread_messages(
        self,
        channel_id: str,
        thread_root_id: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        return await self._request(
            "GET",
            f"/api/v1/channels/{channel_id}/messages/{thread_root_id}/thread?skip=0&limit={limit}",
        )

    async def post_channel_message(
        self,
        channel_id: str,
        content: str,
        *,
        parent_id: Optional[str] = None,
        reply_to_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        return await self._request(
            "POST",
            f"/api/v1/channels/{channel_id}/messages/post",
            json_body=payload,
        )

    async def create_chat_completion(
        self,
        *,
        model_id: str,
        messages: List[Dict[str, str]],
        terminal_id: str,
        skill_ids: List[str],
        tool_ids: List[str],
        tool_server_ids: List[str],
        features: Dict[str, object],
    ) -> str:
        use_native_function_calling = bool(
            terminal_id or skill_ids or tool_ids or tool_server_ids or features
        )
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": use_native_function_calling,
        }
        if tool_ids:
            payload["tool_ids"] = tool_ids
        if tool_server_ids:
            payload["tool_servers"] = tool_server_ids
        if features:
            payload["features"] = features
        if terminal_id:
            payload["terminal_id"] = terminal_id
        if skill_ids:
            payload["skill_ids"] = skill_ids

        if use_native_function_calling:
            payload["params"] = {"function_calling": "native"}

        if use_native_function_calling:
            return await self._run_stateful_chat_completion(payload)

        response = await self._request("POST", "/api/chat/completions", json_body=payload)
        return self.extract_message_content(response)

    async def _run_stateful_chat_completion(self, payload: Dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())
        user_message_id = str(uuid.uuid4())
        assistant_message_id = str(uuid.uuid4())
        now = int(time.time() * 1000)
        user_content = self._last_user_content(payload.get("messages") or [])

        chat_payload = {
            "chat": {
                "id": chat_id,
                "title": "TEAM-BOT Runtime Chat",
                "models": [payload["model"]],
                "history": {
                    "messages": {
                        user_message_id: {
                            "id": user_message_id,
                            "parentId": None,
                            "childrenIds": [assistant_message_id],
                            "role": "user",
                            "content": user_content,
                            "timestamp": now,
                            "models": [payload["model"]],
                        },
                        assistant_message_id: {
                            "id": assistant_message_id,
                            "parentId": user_message_id,
                            "childrenIds": [],
                            "role": "assistant",
                            "content": "",
                            "timestamp": now,
                            "models": [payload["model"]],
                        },
                    },
                    "currentId": assistant_message_id,
                },
                "messages": [
                    {"id": user_message_id, "role": "user", "content": user_content},
                    {"id": assistant_message_id, "role": "assistant", "content": ""},
                ],
                "params": {},
                "timestamp": now,
            }
        }

        created_chat = await self._request("POST", "/api/v1/chats/new", json_body=chat_payload)
        chat_id = self._extract_chat_id(created_chat) or chat_id

        stateful_payload = dict(payload)
        stateful_payload.update(
            {
                "chat_id": chat_id,
                "id": assistant_message_id,
                "session_id": session_id,
                "background_tasks": {
                    "title_generation": False,
                    "tags_generation": False,
                },
            }
        )

        await self._stream_chat_completion(stateful_payload)
        await self._notify_chat_completed(chat_id, assistant_message_id, session_id)
        final_text = await self._wait_for_final_chat_message(chat_id, assistant_message_id)
        if final_text:
            return final_text

        raise RuntimeError("Tool-enabled completion finished without a final assistant message")

    async def _stream_chat_completion(self, payload: Dict[str, Any]) -> str:
        url = f"{self.base_url}/api/chat/completions"
        text_parts: List[str] = []
        tool_names: List[str] = []

        async with self.session.post(url, json=payload) as response:
            if response.status >= 400:
                raw_text = await response.text()
                raise RuntimeError(
                    f"POST /api/chat/completions failed with {response.status}: {raw_text}"
                )

            while True:
                raw_line = await response.content.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue

                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    log.debug("Skipping non-JSON stream chunk: %r", data)
                    continue

                chunk_text = self._extract_stream_text(chunk)
                if chunk_text:
                    text_parts.append(chunk_text)

                tool_names.extend(self._extract_tool_names(chunk))

        combined_text = "".join(text_parts).strip()
        if combined_text:
            return combined_text

        deduped_tool_names = list(dict.fromkeys(name for name in tool_names if name))
        if deduped_tool_names:
            return "도구를 호출했지만 최종 텍스트 응답이 비어 있습니다. 호출된 도구: " + ", ".join(
                deduped_tool_names
            )

        raise RuntimeError("Streaming completion ended without text or tool calls")

    async def _notify_chat_completed(
        self,
        chat_id: str,
        message_id: str,
        session_id: str,
    ) -> None:
        try:
            await self._request(
                "POST",
                "/api/chat/completed",
                json_body={
                    "chat_id": chat_id,
                    "id": message_id,
                    "session_id": session_id,
                },
            )
        except Exception:
            log.debug("Ignoring /api/chat/completed failure", exc_info=True)

    async def _wait_for_final_chat_message(
        self,
        chat_id: str,
        message_id: str,
        *,
        timeout_seconds: float = 15.0,
        poll_interval_seconds: float = 0.5,
    ) -> str:
        deadline = time.monotonic() + timeout_seconds
        last_error: Optional[Exception] = None

        while time.monotonic() < deadline:
            try:
                chat_response = await self._request("GET", f"/api/v1/chats/{chat_id}")
                content = self._extract_chat_message_content(chat_response, message_id)
                if content:
                    return content
            except Exception as exc:
                last_error = exc

            await asyncio.sleep(poll_interval_seconds)

        if last_error is not None:
            raise RuntimeError(f"Failed to fetch final chat message: {last_error}")
        return ""

    @staticmethod
    def extract_message_content(response: Dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError(f"Completion returned no choices: {response}")

        message = choices[0].get("message") or {}
        content = message.get("content")

        extracted = OpenWebUIClient._collect_text(content).strip()
        if extracted:
            return extracted

        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            tool_names = OpenWebUIClient._extract_tool_names({"choices": [{"message": message}]})
            if tool_names:
                deduped_tool_names = list(dict.fromkeys(tool_names))
                return "도구를 호출했지만 최종 텍스트 응답이 비어 있습니다. 호출된 도구: " + ", ".join(
                    deduped_tool_names
                )

        choice_text = OpenWebUIClient._collect_text(choices[0].get("text")).strip()
        if choice_text:
            return choice_text

        raise RuntimeError(f"Completion returned unsupported content: {response}")

    @staticmethod
    def _extract_stream_text(response: Dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            return ""

        choice = choices[0] or {}
        delta = choice.get("delta") or {}

        for candidate in (delta.get("content"), choice.get("message", {}).get("content"), choice.get("text")):
            extracted = OpenWebUIClient._collect_text(candidate).strip()
            if extracted:
                return extracted

        return ""

    @staticmethod
    def _extract_tool_names(response: Dict[str, Any]) -> List[str]:
        choices = response.get("choices") or []
        tool_names: List[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            for container_name in ("delta", "message"):
                container = choice.get(container_name) or {}
                tool_calls = container.get("tool_calls") or []
                if not isinstance(tool_calls, list):
                    continue
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function") or {}
                    name = function.get("name")
                    if isinstance(name, str) and name.strip():
                        tool_names.append(name.strip())
        return tool_names

    @staticmethod
    def _last_user_content(messages: List[Dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content") or "")
        return ""

    @staticmethod
    def _extract_chat_id(response: Any) -> str:
        if isinstance(response, dict):
            if isinstance(response.get("id"), str):
                return response["id"]
            chat = response.get("chat")
            if isinstance(chat, dict) and isinstance(chat.get("id"), str):
                return chat["id"]
        return ""

    @staticmethod
    def _extract_chat_message_content(response: Any, message_id: str) -> str:
        if not isinstance(response, dict):
            return ""

        candidate_chats = [response]
        chat = response.get("chat")
        if isinstance(chat, dict):
            candidate_chats.append(chat)

        for candidate in candidate_chats:
            history = candidate.get("history") or {}
            messages = history.get("messages") or {}
            if isinstance(messages, dict):
                target = messages.get(message_id)
                if isinstance(target, dict):
                    content = OpenWebUIClient._collect_text(target.get("content")).strip()
                    if content:
                        return content

            flat_messages = candidate.get("messages") or []
            if isinstance(flat_messages, list):
                for message in flat_messages:
                    if not isinstance(message, dict):
                        continue
                    if str(message.get("id") or "") != message_id:
                        continue
                    content = OpenWebUIClient._collect_text(message.get("content")).strip()
                    if content:
                        return content

        return ""

    @staticmethod
    def _collect_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = [OpenWebUIClient._collect_text(item) for item in value]
            return "".join(part for part in parts if part)
        if isinstance(value, dict):
            value_type = value.get("type")
            if value_type in {"text", "output_text", "input_text"}:
                text = value.get("text")
                if isinstance(text, str):
                    return text
            for key in ("text", "content", "value", "output"):
                if key in value:
                    nested = OpenWebUIClient._collect_text(value.get(key))
                    if nested:
                        return nested
        return ""

    async def start_typing_loop(
        self,
        sio: Any,
        *,
        channel_id: str,
        message_id: Optional[str],
        stop_event: asyncio.Event,
    ) -> None:
        try:
            while not stop_event.is_set():
                await sio.emit(
                    "events:channel",
                    {
                        "channel_id": channel_id,
                        "message_id": message_id,
                        "data": {"type": "typing", "data": {"typing": True}},
                    },
                )
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=1)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise
