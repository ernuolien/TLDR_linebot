"""FastAPI webhook server and LINE SDK adapter."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhook import WebhookParser
from linebot.v3.webhooks import (
    AudioMessageContent,
    Event,
    FileMessageContent,
    GroupSource,
    ImageMessageContent,
    JoinEvent,
    LeaveEvent,
    LocationMessageContent,
    MessageEvent,
    RoomSource,
    StickerMessageContent,
    TextMessageContent,
    UserMentionee,
    VideoMessageContent,
)

from tldr_linebot.bot import Bot, IncomingMessage
from tldr_linebot.config import Settings
from tldr_linebot.llm import FallbackSummarizer, make_provider
from tldr_linebot.store import Store

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 3600

_PLACEHOLDERS = {
    StickerMessageContent: "[貼圖]",
    ImageMessageContent: "[圖片]",
    VideoMessageContent: "[影片]",
    AudioMessageContent: "[語音]",
    FileMessageContent: "[檔案]",
    LocationMessageContent: "[位置]",
}


class LineMessenger:
    def __init__(self, api: AsyncMessagingApi) -> None:
        self._api = api

    async def reply(self, reply_token: str, text: str) -> None:
        await self._api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )

    async def display_name(self, chat_id: str, is_room: bool, user_id: str) -> str | None:
        if is_room:
            profile = await self._api.get_room_member_profile(chat_id, user_id)
        else:
            profile = await self._api.get_group_member_profile(chat_id, user_id)
        return profile.display_name


def chat_of(event: Event) -> tuple[str | None, bool]:
    source = event.source
    if isinstance(source, GroupSource):
        return source.group_id, False
    if isinstance(source, RoomSource):
        return source.room_id, True
    return None, False


def to_incoming(event: MessageEvent) -> IncomingMessage:
    chat_id, is_room = chat_of(event)
    content = event.message
    is_text = isinstance(content, TextMessageContent)
    text = content.text if is_text else _PLACEHOLDERS.get(type(content), "[其他訊息]")
    mentions: tuple[str, ...] = ()
    if is_text and content.mention:
        mentions = tuple(
            m.user_id
            for m in content.mention.mentionees
            if isinstance(m, UserMentionee) and m.user_id and not m.is_self
        )
    return IncomingMessage(
        chat_id=chat_id,
        is_room=is_room,
        user_id=getattr(event.source, "user_id", None),
        text=text,
        is_text=is_text,
        ts_ms=event.timestamp,
        reply_token=event.reply_token,
        mentions=mentions,
    )


async def handle_events(bot: Bot, events: list[Event]) -> None:
    for event in events:
        try:
            if isinstance(event, MessageEvent):
                await bot.on_message(to_incoming(event))
            elif isinstance(event, JoinEvent):
                await bot.on_join(event.reply_token)
            elif isinstance(event, LeaveEvent):
                chat_id, _ = chat_of(event)
                if chat_id:
                    bot.on_leave(chat_id)
        except Exception:
            logger.exception("failed to handle %s", type(event).__name__)


async def purge_loop(bot: Bot) -> None:
    while True:
        try:
            deleted = bot.purge_expired()
            if deleted:
                logger.info("purged %d expired messages", deleted)
        except Exception:
            logger.exception("purge failed")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    parser = WebhookParser(settings.line_channel_secret)

    providers = [
        make_provider("primary", settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    ]
    if settings.llm_fallback_api_key:
        providers.append(
            make_provider(
                "fallback",
                settings.llm_fallback_base_url,
                settings.llm_fallback_api_key,
                settings.llm_fallback_model,
            )
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(settings.db_path)
        api_client = AsyncApiClient(Configuration(access_token=settings.line_channel_access_token))
        app.state.bot = Bot(
            settings,
            store,
            LineMessenger(AsyncMessagingApi(api_client)),
            FallbackSummarizer(providers),
        )
        purge_task = asyncio.create_task(purge_loop(app.state.bot))
        try:
            yield
        finally:
            purge_task.cancel()
            await api_client.close()
            store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/callback")
    async def callback(
        request: Request,
        background: BackgroundTasks,
        x_line_signature: str = Header(),
    ) -> str:
        body = (await request.body()).decode()
        try:
            events = parser.parse(body, x_line_signature)
        except InvalidSignatureError as exc:
            raise HTTPException(status_code=400, detail="invalid signature") from exc
        background.add_task(handle_events, request.app.state.bot, events)
        return "OK"

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, proxy_headers=True)
