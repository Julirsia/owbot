from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover - runtime dependency loaded via requirements
    aiohttp = None  # type: ignore[assignment]


log = logging.getLogger(__name__)


class OpenWebUIClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: int,
        tool_timeout_seconds: int,
    ) -> None:
        if aiohttp is None:
            raise RuntimeError("aiohttp is required to use OpenWebUIClient")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.tool_timeout_seconds = tool_timeout_seconds
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
        timeout_seconds: Optional[int] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        request_timeout = None
        if timeout_seconds is not None:
            request_timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        try:
            async with self.session.request(
                method,
                url,
                json=json_body,
                timeout=request_timeout,
            ) as response:
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
                    log.error(
                        "Open WebUI request failed method=%s path=%s status=%s body=%s response=%s",
                        method,
                        path,
                        response.status,
                        self._summarize_payload(json_body),
                        self._safe_repr(data),
                    )
                    raise RuntimeError(f"{method} {path} failed with {response.status}: {data}")
                return data
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"{method} {path} timed out after {timeout_seconds or self.timeout.total} seconds"
            ) from exc

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
        explicit_tool_ids_only = bool(tool_ids)
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
        if tool_server_ids and not explicit_tool_ids_only:
            payload["tool_servers"] = tool_server_ids
        if features and not explicit_tool_ids_only:
            payload["features"] = features
        if terminal_id and not explicit_tool_ids_only:
            payload["terminal_id"] = terminal_id
        if skill_ids and not explicit_tool_ids_only:
            payload["skill_ids"] = skill_ids

        if use_native_function_calling:
            payload["params"] = {"function_calling": "native"}

        log.debug(
            "Posting chat completion model=%s native=%s payload=%s",
            model_id,
            use_native_function_calling,
            self._summarize_payload(payload),
        )
        if use_native_function_calling:
            return await self._stream_chat_completion(payload)

        response = await self._request(
            "POST",
            "/api/chat/completions",
            json_body=payload,
        )
        log.debug(
            "Direct completion summary has_text=%s tool_names=%s",
            bool(self._extract_message_text_or_empty(response)),
            self._extract_tool_names(response),
        )
        return self.extract_message_content(response)

    async def _stream_chat_completion(self, payload: Dict[str, Any]) -> str:
        url = f"{self.base_url}/api/chat/completions"
        request_timeout = aiohttp.ClientTimeout(total=self.tool_timeout_seconds)
        try:
            async with self.session.request(
                "POST",
                url,
                json=payload,
                timeout=request_timeout,
            ) as response:
                if response.status >= 400:
                    raw_text = await response.text()
                    data = self._decode_response_body(raw_text)
                    log.error(
                        "Open WebUI request failed method=%s path=%s status=%s body=%s response=%s",
                        "POST",
                        "/api/chat/completions",
                        response.status,
                        self._summarize_payload(payload),
                        self._safe_repr(data),
                    )
                    raise RuntimeError(
                        f"POST /api/chat/completions failed with {response.status}: {data}"
                    )

                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" not in content_type.lower():
                    raw_text = await response.text()
                    data = self._decode_response_body(raw_text)
                    log.debug(
                        "Native completion returned non-SSE content-type=%s has_text=%s tool_names=%s",
                        content_type,
                        bool(self._extract_message_text_or_empty(data)),
                        self._extract_tool_names(data) if isinstance(data, dict) else [],
                    )
                    if not isinstance(data, dict):
                        raise RuntimeError(
                            "Streaming completion returned a non-JSON non-SSE response"
                        )
                    return self.extract_message_content(data)

                text_parts: List[str] = []
                terminal_message_text: str = ""
                tool_names: List[str] = []
                async for event in self._iter_sse_events(response):
                    if event == "[DONE]":
                        break

                    payload_data = self._decode_response_body(event)
                    if not isinstance(payload_data, dict):
                        log.debug(
                            "Skipping non-JSON SSE payload from chat completion: %s",
                            self._safe_repr(payload_data),
                        )
                        continue

                    event_tool_names = self._extract_tool_names(payload_data)
                    if event_tool_names:
                        tool_names.extend(event_tool_names)
                        log.debug(
                            "Observed intermediate tool_calls while waiting for final text: %s",
                            event_tool_names,
                        )

                    delta_text = self._extract_stream_delta_text(payload_data)
                    if delta_text:
                        text_parts.append(delta_text)
                        continue

                    message_text = self._extract_stream_message_text(payload_data)
                    if message_text:
                        terminal_message_text = message_text

                final_text = "".join(text_parts).strip() or terminal_message_text.strip()
                deduped_tool_names = list(dict.fromkeys(tool_names))
                log.debug(
                    "Streamed completion summary has_text=%s tool_names=%s",
                    bool(final_text),
                    deduped_tool_names,
                )
                if final_text:
                    return final_text
                if deduped_tool_names:
                    return (
                        "도구를 호출했지만 최종 텍스트 응답이 비어 있습니다. 호출된 도구: "
                        + ", ".join(deduped_tool_names)
                    )
                raise RuntimeError("Streaming completion ended without text or tool calls")
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"POST /api/chat/completions timed out after {self.tool_timeout_seconds} seconds"
            ) from exc

    @staticmethod
    def extract_message_content(response: Dict[str, Any]) -> str:
        extracted = OpenWebUIClient._extract_message_text_or_empty(response)
        if extracted:
            return extracted

        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError(f"Completion returned no choices: {response}")

        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            tool_names = OpenWebUIClient._extract_tool_names({"choices": [{"message": message}]})
            if tool_names:
                deduped_tool_names = list(dict.fromkeys(tool_names))
                return "도구를 호출했지만 최종 텍스트 응답이 비어 있습니다. 호출된 도구: " + ", ".join(
                    deduped_tool_names
                )

        raise RuntimeError(f"Completion returned unsupported content: {response}")

    @staticmethod
    async def _iter_sse_events(response: aiohttp.ClientResponse) -> AsyncIterator[str]:
        buffer = ""
        event_lines: List[str] = []

        async for chunk in response.content.iter_any():
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.rstrip("\r")
                if not line:
                    payload = OpenWebUIClient._flush_sse_event_lines(event_lines)
                    event_lines.clear()
                    if payload is not None:
                        yield payload
                    continue
                event_lines.append(line)

        trailing = buffer.rstrip("\r")
        if trailing:
            event_lines.append(trailing)
        payload = OpenWebUIClient._flush_sse_event_lines(event_lines)
        if payload is not None:
            yield payload

    @staticmethod
    def _flush_sse_event_lines(event_lines: List[str]) -> Optional[str]:
        if not event_lines:
            return None

        data_lines: List[str] = []
        for line in event_lines:
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            return None
        return "\n".join(data_lines)

    @staticmethod
    def _extract_message_text_or_empty(response: Any) -> str:
        if isinstance(response, dict):
            for candidate in (
                response.get("message"),
                response.get("content"),
                response.get("text"),
                response.get("response"),
                response.get("data"),
            ):
                extracted = OpenWebUIClient._collect_text(candidate).strip()
                if extracted:
                    return extracted

            choices = response.get("choices") or []
            if isinstance(choices, list) and choices:
                choice = choices[0] or {}
                message = choice.get("message") or {}
                for candidate in (
                    message.get("content"),
                    message.get("text"),
                    choice.get("text"),
                    choice.get("content"),
                    choice.get("response"),
                ):
                    extracted = OpenWebUIClient._collect_text(candidate).strip()
                    if extracted:
                        return extracted

        return ""

    @staticmethod
    def _extract_stream_delta_text(response: Any) -> str:
        if not isinstance(response, dict):
            return ""

        parts: List[str] = []
        choices = response.get("choices") or []
        if not isinstance(choices, list):
            return ""
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                continue
            for candidate in (delta.get("content"), delta.get("text"), delta.get("response")):
                extracted = OpenWebUIClient._collect_text(candidate)
                if extracted:
                    parts.append(extracted)
        return "".join(parts).strip()

    @staticmethod
    def _extract_stream_message_text(response: Any) -> str:
        if not isinstance(response, dict):
            return ""

        for candidate in (
            response.get("message"),
            response.get("content"),
            response.get("text"),
            response.get("response"),
        ):
            extracted = OpenWebUIClient._collect_text(candidate).strip()
            if extracted:
                return extracted

        choices = response.get("choices") or []
        if not isinstance(choices, list):
            return ""
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            for candidate in (
                message.get("content"),
                message.get("text"),
                choice.get("text"),
                choice.get("content"),
                choice.get("response"),
            ):
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

    @staticmethod
    def _summarize_payload(payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload

        summary: Dict[str, Any] = {}
        for key, value in payload.items():
            if key == "messages" and isinstance(value, list):
                summary[key] = {
                    "count": len(value),
                    "roles": [message.get("role") for message in value if isinstance(message, dict)],
                }
                continue
            if key in {"tool_ids", "tool_servers", "skill_ids"} and isinstance(value, list):
                summary[key] = value
                continue
            if key == "features" and isinstance(value, dict):
                summary[key] = sorted(value.keys())
                continue
            summary[key] = value
        return summary

    @staticmethod
    def _safe_repr(value: Any, limit: int = 2000) -> str:
        rendered = repr(value)
        if len(rendered) > limit:
            return rendered[: limit - 3] + "..."
        return rendered

    @staticmethod
    def _decode_response_body(raw_text: str) -> Any:
        if not raw_text.strip():
            return None
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text

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
