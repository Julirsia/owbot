from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp


log = logging.getLogger(__name__)


class OpenWebUIClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: int) -> None:
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
            try:
                data = await response.json(content_type=None)
            except aiohttp.ContentTypeError:
                data = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"{method} {path} failed with {response.status}: {data}")
            return data

    async def get_channel_messages(self, channel_id: str, limit: int) -> List[Dict[str, Any]]:
        return await self._request(
            "GET",
            f"/api/v1/channels/{channel_id}/messages?skip=0&limit={limit}",
        )

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
        tool_ids: List[str],
        tool_server_ids: List[str],
        features: Dict[str, object],
    ) -> str:
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": False,
            "tool_ids": tool_ids,
            "tool_servers": tool_server_ids or None,
            "features": features,
        }

        if tool_ids or tool_server_ids or features:
            payload["params"] = {"function_calling": "native"}

        response = await self._request("POST", "/api/chat/completions", json_body=payload)
        return self.extract_message_content(response)

    @staticmethod
    def extract_message_content(response: Dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError(f"Completion returned no choices: {response}")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            joined = "".join(parts).strip()
            if joined:
                return joined

        raise RuntimeError(f"Completion returned unsupported content: {response}")

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
