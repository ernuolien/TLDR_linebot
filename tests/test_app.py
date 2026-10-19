import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from tldr_linebot import app as app_module
from tldr_linebot.bot import IncomingMessage


def sign(body: str, secret: str = "secret") -> str:
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def message_event(message: dict) -> dict:
    return {
        "type": "message",
        "mode": "active",
        "timestamp": 1767225600000,
        "webhookEventId": "01H000000000000000000000",
        "deliveryContext": {"isRedelivery": False},
        "replyToken": "rt",
        "source": {"type": "group", "groupId": "g1", "userId": "u1"},
        "message": message,
    }


@pytest.fixture
def client_and_calls(settings, monkeypatch):
    calls = []

    async def fake_handle(bot, events):
        calls.extend(events)

    monkeypatch.setattr(app_module, "handle_events", fake_handle)
    with TestClient(app_module.create_app(settings)) as client:
        yield client, calls


def test_rejects_bad_signature(client_and_calls):
    client, calls = client_and_calls
    body = json.dumps({"destination": "x", "events": []})
    response = client.post("/callback", content=body, headers={"X-Line-Signature": "bad"})
    assert response.status_code == 400
    assert calls == []


def test_accepts_signed_webhook(client_and_calls):
    client, calls = client_and_calls
    event = message_event({"type": "text", "id": "1", "quoteToken": "q", "text": "hi"})
    body = json.dumps({"destination": "x", "events": [event]})
    response = client.post("/callback", content=body, headers={"X-Line-Signature": sign(body)})
    assert response.status_code == 200
    assert len(calls) == 1


def test_to_incoming_maps_text_and_placeholders(settings):
    from linebot.v3.webhook import WebhookParser

    parser = WebhookParser("secret")
    text = message_event({"type": "text", "id": "1", "quoteToken": "q", "text": "hi"})
    sticker = message_event(
        {
            "type": "sticker",
            "id": "2",
            "quoteToken": "q",
            "packageId": "1",
            "stickerId": "1",
            "stickerResourceType": "STATIC",
        }
    )
    body = json.dumps({"destination": "x", "events": [text, sticker]})
    events = parser.parse(body, sign(body))

    assert app_module.to_incoming(events[0]) == IncomingMessage(
        chat_id="g1",
        is_room=False,
        user_id="u1",
        text="hi",
        is_text=True,
        ts_ms=1767225600000,
        reply_token="rt",
    )
    assert app_module.to_incoming(events[1]).text == "[貼圖]"


def test_to_incoming_extracts_user_mentions_but_not_the_bot():
    from linebot.v3.webhook import WebhookParser

    parser = WebhookParser("secret")
    text = message_event(
        {
            "type": "text",
            "id": "1",
            "quoteToken": "q",
            "text": "@Bot tldr @小華 @All",
            "mention": {
                "mentionees": [
                    {"type": "user", "index": 0, "length": 4, "userId": "bot", "isSelf": True},
                    {"type": "user", "index": 10, "length": 3, "userId": "u2", "isSelf": False},
                    {"type": "all", "index": 14, "length": 4},
                ]
            },
        }
    )
    body = json.dumps({"destination": "x", "events": [text]})
    events = parser.parse(body, sign(body))
    assert app_module.to_incoming(events[0]).mentions == ("u2",)
