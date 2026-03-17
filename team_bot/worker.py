from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import socketio

from .config import BotConfig
from .context_builder import (
    SYSTEM_PROMPT,
    build_invocation_context,
    extract_mentions,
    message_invokes_bot,
    message_mentions_bot,
    message_mentions_bot_display_name,
)
from .openwebui_client import OpenWebUIClient
from .state import SQLiteStateStore


log = logging.getLogger(__name__)
CHANNEL_EVENT_NAMES = ("events:channel", "channel-events")


class TeamBotWorker:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.state = SQLiteStateStore(config.state_db_path)
        if config.socketio_debug:
            logging.getLogger("socketio").setLevel(logging.DEBUG)
            logging.getLogger("engineio").setLevel(logging.DEBUG)
        self.sio = socketio.AsyncClient(
            logger=config.socketio_debug,
            engineio_logger=config.socketio_debug,
            reconnection=True,
        )
        self.client = OpenWebUIClient(
            config.base_url,
            config.bot_token,
            timeout_seconds=config.completion_timeout_seconds,
            tool_timeout_seconds=config.tool_timeout_seconds,
            final_message_wait_seconds=config.final_message_wait_seconds,
        )
        self._heartbeat_task: Optional[asyncio.Task[Any]] = None
        self._ws_token = config.bot_session_token or ""
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.sio.event
        async def connect() -> None:
            log.info(
                "Connected to Open WebUI websocket sid=%s base_url=%s",
                self.sio.sid,
                self.config.base_url,
            )
            log.info(
                "Worker identity config bot_user_id=%r bot_display_name=%r model_id=%r",
                self.config.bot_user_id,
                self.config.bot_display_name,
                self.config.model_id,
            )

            async def join_callback(data: Optional[Dict[str, Any]] = None) -> None:
                if data is not None:
                    log.info("Authenticated as %s", data)
                else:
                    log.info("Authenticated without callback payload")

            await self.sio.emit(
                "user-join",
                {"auth": {"token": self._ws_token}},
                callback=join_callback,
            )
            try:
                current_user = await self.client.get_current_user()
                actual_user_id = str(current_user.get("id") or "")
                actual_user_name = str(current_user.get("name") or "")
                log.info(
                    "Authenticated bot identity actual_user_id=%r actual_user_name=%r role=%r",
                    actual_user_id,
                    actual_user_name,
                    current_user.get("role"),
                )
                if actual_user_id and actual_user_id != self.config.bot_user_id:
                    log.warning(
                        "Configured OPENWEBUI_BOT_USER_ID=%r does not match token owner id=%r",
                        self.config.bot_user_id,
                        actual_user_id,
                    )
                if (
                    self.config.bot_display_name
                    and actual_user_name
                    and actual_user_name != self.config.bot_display_name
                ):
                    log.warning(
                        "Configured OPENWEBUI_BOT_DISPLAY_NAME=%r does not match token owner name=%r",
                        self.config.bot_display_name,
                        actual_user_name,
                    )
                channels = await self.client.get_channels()
                log.info("Bot can access %s channels", len(channels))
                if not channels:
                    log.warning(
                        "Bot currently sees no channels. Check channel membership and features.channels permission."
                    )
                else:
                    channel_preview = [
                        {
                            "id": channel.get("id"),
                            "name": channel.get("name"),
                            "type": channel.get("type"),
                        }
                        for channel in channels[:10]
                    ]
                    log.info("Accessible channel preview: %s", channel_preview)
            except Exception:
                log.exception("Failed to fetch accessible channels after websocket connect")
            self._start_heartbeat_loop()

        @self.sio.event
        async def connect_error(data: Any) -> None:
            log.error("Socket connection error: %r", data)

        @self.sio.event
        async def disconnect() -> None:
            log.warning("Disconnected from Open WebUI websocket")
            await self._stop_heartbeat_loop()

        async def on_channel_event(event_name: str, event: Dict[str, Any]) -> None:
            if self.config.log_raw_channel_events:
                log.info("Raw %s payload: %s", event_name, self._safe_repr(event))
            event_type = ((event.get("data") or {}).get("type")) or "unknown"
            channel_id = event.get("channel_id")
            log.debug(
                "Received channel event name=%s type=%s channel_id=%s",
                event_name,
                event_type,
                channel_id,
            )
            await self.handle_channel_event(event)

        def make_channel_handler(event_name: str):
            async def _handler(event: Dict[str, Any]) -> None:
                await on_channel_event(event_name, event)

            return _handler

        for event_name in CHANNEL_EVENT_NAMES:
            self.sio.on(event_name, handler=make_channel_handler(event_name))

        @self.sio.on("*")
        async def on_any_event(event: str, *args: Any) -> None:
            if event in CHANNEL_EVENT_NAMES:
                return
            if not self.config.socketio_debug:
                return
            preview = self._safe_repr(args)
            log.debug("Received non-channel socket event name=%s args=%s", event, preview)

    async def run(self) -> None:
        async with self.client:
            self._ws_token = await self._resolve_websocket_token()
            await self.sio.connect(
                self.config.base_url,
                socketio_path="/ws/socket.io",
                transports=["websocket"],
                auth={"token": self._ws_token},
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
                    {"auth": {"token": self._ws_token}},
                )
                log.debug("Sent heartbeat and join-channels")
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise

    async def _resolve_websocket_token(self) -> str:
        if self.config.bot_session_token:
            log.info("Using OPENWEBUI_BOT_SESSION_TOKEN for websocket authentication")
            return self.config.bot_session_token

        if self.config.bot_email and self.config.bot_password:
            log.info("Signing in with OPENWEBUI_BOT_EMAIL to acquire websocket session token")
            return await self.client.sign_in(self.config.bot_email, self.config.bot_password)

        if self.config.bot_token.startswith("sk-"):
            log.warning(
                "OPENWEBUI_BOT_TOKEN looks like an API key. Open WebUI websocket auth expects a JWT session token."
            )
        else:
            log.info("Using OPENWEBUI_BOT_TOKEN for websocket authentication")
        return self.config.bot_token

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
            "Message received id=%s parent_id=%s reply_to_id=%s user=%s role=%s",
            message.get("id"),
            message.get("parent_id"),
            message.get("reply_to_id"),
            user.get("name") or user.get("id"),
            user.get("role"),
        )
        if self.config.log_message_content:
            log.info("Message content id=%s content=%r", message.get("id"), content)

        structured_match = message_mentions_bot(content, self.config.bot_user_id)
        display_match = message_mentions_bot_display_name(content, self.config.bot_display_name)
        mentions = extract_mentions(content)
        log.debug(
            "Mention analysis id=%s structured_match=%s display_match=%s mentions=%s",
            message.get("id"),
            structured_match,
            display_match,
            mentions,
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
                terminal_id=self.config.terminal_id,
                skill_ids=self.config.skill_ids,
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

    @staticmethod
    def _safe_repr(value: Any, limit: int = 4000) -> str:
        rendered = repr(value)
        if len(rendered) > limit:
            return rendered[: limit - 3] + "..."
        return rendered
