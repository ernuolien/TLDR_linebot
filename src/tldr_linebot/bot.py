"""Bot behaviour, independent of the LINE SDK so it can be tested in isolation."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from tldr_linebot import command
from tldr_linebot.config import Settings
from tldr_linebot.llm import SummarizeError, Summarizer
from tldr_linebot.prompt import SYSTEM_PROMPT, build_chat_log, build_user_prompt
from tldr_linebot.store import Store, to_ms

logger = logging.getLogger(__name__)

JOIN_NOTICE = (
    "大家好，我是 TL;DR 摘要機器人 👋\n"
    "我會記錄本群組的訊息並保留 7 天，只用於產生摘要；超過 7 天自動刪除，"
    "把我移出群組則立即刪除本群組的所有紀錄。\n\n" + command.USAGE
)
DIRECT_CHAT_REPLY = "請把我加入群組再使用喔！\n\n" + command.USAGE
EMPTY_REPLY = "這段時間內沒有可以摘要的訊息。"
FAILURE_REPLY = "摘要失敗，請稍後再試。"
UNKNOWN_NAME = "某位成員"
LINE_TEXT_LIMIT = 5000


class Messenger(Protocol):
    async def reply(self, reply_token: str, text: str) -> None: ...

    async def display_name(self, chat_id: str, is_room: bool, user_id: str) -> str | None: ...


@dataclass(frozen=True)
class IncomingMessage:
    chat_id: str | None  # None for one-on-one chats
    is_room: bool
    user_id: str | None
    text: str  # message text, or a placeholder such as "[貼圖]"
    is_text: bool
    ts_ms: int
    reply_token: str | None


class Bot:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        messenger: Messenger,
        summarizer: Summarizer,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._store = store
        self._messenger = messenger
        self._summarizer = summarizer
        self._clock = clock
        self._names: dict[tuple[str, str], tuple[str, float]] = {}
        self._last_tldr: dict[str, float] = {}

    async def on_message(self, msg: IncomingMessage) -> None:
        cmd = None
        if msg.is_text:
            cmd = command.parse(
                msg.text,
                default=timedelta(hours=self._settings.default_window_hours),
                maximum=self._settings.retention,
            )

        if msg.chat_id is None:
            if msg.reply_token:
                await self._messenger.reply(msg.reply_token, DIRECT_CHAT_REPLY)
            return

        if cmd is None:
            name = await self._name(msg.chat_id, msg.is_room, msg.user_id)
            self._store.add(msg.chat_id, msg.user_id or "", name, msg.text, msg.ts_ms)
            return

        if msg.reply_token is None:
            return
        if isinstance(cmd, command.InvalidCommand):
            await self._messenger.reply(msg.reply_token, cmd.reason)
            return

        now = self._clock()
        last = self._last_tldr.get(msg.chat_id)
        if last is not None and now - last < self._settings.cooldown_seconds:
            wait = int(self._settings.cooldown_seconds - (now - last)) + 1
            await self._messenger.reply(msg.reply_token, f"請稍候 {wait} 秒再試。")
            return
        self._last_tldr[msg.chat_id] = now

        text = await self._summarize(msg.chat_id, cmd.window, now)
        await self._messenger.reply(msg.reply_token, text[:LINE_TEXT_LIMIT])

    async def on_join(self, reply_token: str | None) -> None:
        if reply_token:
            await self._messenger.reply(reply_token, JOIN_NOTICE)

    def on_leave(self, chat_id: str) -> None:
        deleted = self._store.delete_chat(chat_id)
        self._names = {k: v for k, v in self._names.items() if k[0] != chat_id}
        self._last_tldr.pop(chat_id, None)
        logger.info("left chat %s, deleted %d messages", chat_id, deleted)

    def purge_expired(self) -> int:
        cutoff = datetime.fromtimestamp(self._clock(), UTC) - self._settings.retention
        return self._store.delete_older_than(to_ms(cutoff))

    async def _summarize(self, chat_id: str, window: timedelta, now: float) -> str:
        since = datetime.fromtimestamp(now, UTC) - window
        messages, total = self._store.since(chat_id, to_ms(since), self._settings.max_messages)
        if not messages:
            return EMPTY_REPLY

        chat_log, included = build_chat_log(
            messages, self._settings.tz, self._settings.max_input_chars
        )
        try:
            summary = await self._summarizer.summarize(SYSTEM_PROMPT, build_user_prompt(chat_log))
        except SummarizeError:
            logger.exception("summarization failed for chat %s", chat_id)
            return FAILURE_REPLY

        if included < total:
            return f"（訊息過多，僅摘要最近 {included} 則，共 {total} 則）\n\n{summary}"
        return summary

    async def _name(self, chat_id: str, is_room: bool, user_id: str | None) -> str:
        if not user_id:
            return UNKNOWN_NAME
        key = (chat_id, user_id)
        now = self._clock()
        cached = self._names.get(key)
        if cached and now - cached[1] < self._settings.name_cache_hours * 3600:
            return cached[0]
        try:
            name = await self._messenger.display_name(chat_id, is_room, user_id)
        except Exception:
            logger.warning("failed to fetch display name for %s", user_id, exc_info=True)
            name = None
        if name is None:
            return cached[0] if cached else UNKNOWN_NAME
        self._names[key] = (name, now)
        return name
