from types import SimpleNamespace

import httpx
import openai
import pytest

from tldr_linebot.llm import FallbackSummarizer, Provider, SummarizeError


class FakeCompletions:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        message = SimpleNamespace(content=self.result)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def provider(name, result):
    completions = FakeCompletions(result)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return Provider(name=name, client=client, model="m"), completions


def rate_limit():
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError("rate limited", response=response, body=None)


async def test_uses_primary_when_it_works():
    primary, _ = provider("p", "summary")
    fallback, f_calls = provider("f", "other")
    assert await FallbackSummarizer([primary, fallback]).summarize("s", "u") == "summary"
    assert f_calls.calls == 0


async def test_logs_which_model_answered(caplog):
    primary, _ = provider("p", "")
    fallback, _ = provider("f", "summary")
    with caplog.at_level("INFO", logger="tldr_linebot.llm"):
        await FallbackSummarizer([primary, fallback]).summarize("s", "u")
    assert "answered by provider f (model m)" in caplog.text


async def test_falls_back_on_rate_limit():
    primary, _ = provider("p", rate_limit())
    fallback, _ = provider("f", "from fallback")
    assert await FallbackSummarizer([primary, fallback]).summarize("s", "u") == "from fallback"


async def test_falls_back_on_empty_content():
    primary, _ = provider("p", "  ")
    fallback, _ = provider("f", "ok")
    assert await FallbackSummarizer([primary, fallback]).summarize("s", "u") == "ok"


async def test_raises_when_all_fail():
    primary, _ = provider("p", rate_limit())
    fallback, _ = provider("f", rate_limit())
    with pytest.raises(SummarizeError):
        await FallbackSummarizer([primary, fallback]).summarize("s", "u")
