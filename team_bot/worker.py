from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import socketio

from .config import BotConfig
from .context_builder import (
    SYSTEM_PROMPT,
    build_invocation_context,
    message_invokes_bot,
)
from .openwebui_client import OpenWebUIClient
from .state import SQLiteStateStore


log = logging.getLogger(__name__)


class TeamBotWorker:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.state = SQLiteStateStore(config.state_db_path)
        self.sio = socketio.AsyncClient(logger=False, engineio_logger=False, reconnection=True)
        self.client = OpenWebUIClient(
            config.base_url,
            config.bot_token,
            timeout_seconds=config.completion_timeout_seconds,
        )
        self._heartbeat_task: Optional[asyncio.Task[Any]] = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.sio.event
        async def connect() -> None:
            log.info("Connected to Open WebUI websocket")

            async def join_callback(data: Optional[Dict[str, Any]] = None) -> None:
                if data is not None:
                    log.info("Authenticated as %s", data)
                else:
                    log.info("Authenticated without callback payload")

            await self.sio.emit(
                "user-join",
                {"auth": {"token": self.config.bot_token}},
                callback=join_callback,
            )
            try:
                channels = await self.client.get_channels()
                log.info("Bot can access %s channels", len(channels))
                if not channels:
                    log.warning(
                        "Bot currently sees no channels. Check channel membership and features.channels permission."
                    )
            except Exception:
                log.exception("Failed to fetch accessible channels after websocket connect")
            self._start_heartbeat_loop()

        @self.sio.event
        async def disconnect() -> None:
            log.warning("Disconnected from Open WebUI websocket")
            await self._stop_heartbeat_loop()

        @self.sio.on("events:channel")
        async def on_channel_event(event: Dict[str, Any]) -> None:
            event_type = ((event.get("data") or {}).get("type")) or "unknown"
            channel_id = event.get("channel_id")
            log.debug("Received channel event type=%s channel_id=%s", event_type, channel_id)
            await self.handle_channel_event(event)

    async def run(self) -> None:
        async with self.client:
            await self.sio.connect(
                self.config.base_url,
                socketio_path="/ws/socket.io",
                transports=["websocket"],
            )
            await self.sio.wait()

    def _start_heartbeat_loop(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat_loop(self) -> None:
        if self._heartbeat_task is None:
            return
        self._heartbeat_task.cancel()
        try:
            await self._heartbeat_task
        except asyncio.CancelledError:
            pass
        self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        try:
            log.info("Heartbeat loop started")
            while True:
                await self.sio.emit("heartbeat", {})
                await self.sio.emit(
                    "join-channels",
                    {"auth": {"token": self.config.bot_token}},
                )
                log.debug("Sent heartbeat and join-channels")
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise

    async def handle_channel_event(self, event: Dict[str, Any]) -> None:
        event_data = event.get("data") or {}
        event_type = event_data.get("type")
        if event_type != "message":
            return

        message = event_data.get("data") or {}
        user = event.get("user") or {}
        if str(user.get("id") or "") == self.config.bot_user_id:
            log.debug("Skipping bot's own message id=%s", message.get("id"))
            return
        if user.get("role") == "webhook":
            log.debug("Skipping webhook message id=%s", message.get("id"))
            return

        content = str(message.get("content") or "")
        log.debug(
            "Message received id=%s user=%s content=%r",
            message.get("id"),
            user.get("name") or user.get("id"),
            content,
        )
        if not message_invokes_bot(
            content,
            self.config.bot_user_id,
            self.config.bot_display_name,
        ):
            log.debug("Skipping non-bot-invocation message id=%s", message.get("id"))
            return

        dedupe_key = self._dedupe_key(event)
        if not self.state.claim(dedupe_key):
            log.debug("Skipping duplicate channel event: %s", dedupe_key)
            return

        log.info(
            "Accepted bot invocation channel_id=%s message_id=%s user=%s",
            event.get("channel_id"),
            message.get("id"),
            user.get("name") or user.get("id"),
        )
        asyncio.create_task(self.process_invocation(event, message))

    def _dedupe_key(self, event: Dict[str, Any]) -> str:
        message = (event.get("data") or {}).get("data") or {}
        updated_at = message.get("updated_at") or message.get("created_at") or 0
        return f"{event.get('channel_id')}:{message.get('id')}:{updated_at}"

    async def process_invocation(self, event: Dict[str, Any], message: Dict[str, Any]) -> None:
        channel_id = str(event["channel_id"])
        thread_root_id = message.get("parent_id")
        typing_stop = asyncio.Event()
        typing_task = asyncio.create_task(
            self.client.start_typing_loop(
                self.sio,
                channel_id=channel_id,
                message_id=str(thread_root_id or message.get("id")),
                stop_event=typing_stop,
            )
        )

        try:
            log.info(
                "Processing invocation channel_id=%s message_id=%s thread_root_id=%s",
                channel_id,
                message.get("id"),
                thread_root_id,
            )
            context = await self._load_context(channel_id, message, thread_root_id)
            completion = await self.client.create_chat_completion(
                model_id=self.config.model_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": context.prompt},
                ],
                tool_ids=self.config.tool_ids,
                tool_server_ids=self.config.tool_server_ids,
                features=self.config.features,
            )

            completion = completion.strip()
            if not completion:
                completion = "응답을 생성하지 못했습니다. 한 번 더 호출해 주세요."

            log.info(
                "Posting response channel_id=%s reply_to_id=%s parent_id=%s",
                channel_id,
                message.get("id"),
                context.thread_root_id,
            )
            await self.client.post_channel_message(
                channel_id,
                completion,
                parent_id=context.thread_root_id,
                reply_to_id=str(message.get("id")) if message.get("id") else None,
            )
        except Exception as exc:
            log.exception("Failed to process invocation")
            await self.client.post_channel_message(
                channel_id,
                f"요청을 처리하지 못했습니다: {exc}",
                parent_id=str(thread_root_id) if thread_root_id else None,
                reply_to_id=str(message.get("id")) if message.get("id") else None,
            )
        finally:
            typing_stop.set()
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    async def _load_context(
        self,
        channel_id: str,
        invocation_message: Dict[str, Any],
        thread_root_id: Optional[str],
    ):
        recent_channel_messages = await self.client.get_channel_messages(
            channel_id, self.config.channel_context_limit
        )

        thread_root_message = None
        thread_messages: List[Dict[str, Any]] = []
        if thread_root_id:
            thread_root_message = await self.client.get_channel_message(channel_id, str(thread_root_id))
            thread_messages = await self.client.get_thread_messages(
                channel_id,
                str(thread_root_id),
                self.config.thread_context_limit,
            )

        return build_invocation_context(
            invocation_message=invocation_message,
            recent_channel_messages=recent_channel_messages,
            thread_root_message=thread_root_message,
            thread_messages=thread_messages,
            bot_user_id=self.config.bot_user_id,
        )
