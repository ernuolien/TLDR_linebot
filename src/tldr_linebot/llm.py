"""Summarization through OpenAI-compatible endpoints, with provider fallback."""

import logging
from dataclasses import dataclass
from typing import Protocol

import openai

logger = logging.getLogger(__name__)


class Summarizer(Protocol):
    async def summarize(self, system: str, user: str) -> str: ...


class SummarizeError(Exception):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    client: openai.AsyncOpenAI
    model: str


class FallbackSummarizer:
    """Tries each provider in order; raises SummarizeError if all fail."""

    def __init__(self, providers: list[Provider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = providers

    async def summarize(self, system: str, user: str) -> str:
        for provider in self._providers:
            try:
                response = await provider.client.chat.completions.create(
                    model=provider.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    return content.strip()
                logger.warning("provider %s returned empty content", provider.name)
            except openai.APIError as exc:
                logger.warning("provider %s failed: %s", provider.name, exc)
        raise SummarizeError("all providers failed")


def make_provider(name: str, base_url: str, api_key: str, model: str) -> Provider:
    client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=45, max_retries=1)
    return Provider(name=name, client=client, model=model)
