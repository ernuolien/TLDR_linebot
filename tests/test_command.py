from datetime import timedelta

import pytest

from tldr_linebot.command import InvalidCommand, TldrCommand, parse

DEFAULT = timedelta(hours=12)
MAXIMUM = timedelta(days=7)


def p(text: str):
    return parse(text, DEFAULT, MAXIMUM)


@pytest.mark.parametrize("text", ["hello", "", "tldr", "看一下 /tldr"])
def test_non_commands(text):
    assert p(text) is None


@pytest.mark.parametrize(
    ("text", "window"),
    [
        ("/tldr", DEFAULT),
        ("  /TLDR  ", DEFAULT),
        ("/tldr 3h", timedelta(hours=3)),
        ("/tldr 2D", timedelta(days=2)),
        ("/tldr 7d", timedelta(days=7)),
        ("/tldr 168h", timedelta(days=7)),
    ],
)
def test_valid(text, window):
    assert p(text) == TldrCommand(window)


@pytest.mark.parametrize(
    "text", ["/tldr 0h", "/tldr 8d", "/tldr 169h", "/tldr 200", "/tldr 3m", "/tldr 1h 2h", "/tldrx"]
)
def test_invalid(text):
    assert isinstance(p(text), InvalidCommand)
