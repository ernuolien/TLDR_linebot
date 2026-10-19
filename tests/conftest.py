import pytest

from tldr_linebot.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        line_channel_secret="secret",
        line_channel_access_token="token",
        llm_api_key="key",
        db_path=":memory:",
    )
