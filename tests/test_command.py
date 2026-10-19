from datetime import timedelta

import pytest

from tldr_linebot.command import InvalidCommand, TldrCommand, describe_window, parse

DEFAULT = timedelta(hours=3)
MAXIMUM = timedelta(days=7)


def p(text: str):
    return parse(text, DEFAULT, MAXIMUM)


@pytest.mark.parametrize(
    "text",
    [
        "hello",
        "",
        "看一下 tldr",
        "tldrx",
        "/tldrx",
    ],
)
def test_non_commands(text):
    assert p(text) is None


@pytest.mark.parametrize(
    ("text", "window"),
    [
        ("tldr", DEFAULT),
        ("  TLDR  ", DEFAULT),
        ("/tldr", DEFAULT),
        ("tldr 3h", timedelta(hours=3)),
        ("/tldr 3h", timedelta(hours=3)),
        ("Tldr 2D", timedelta(days=2)),
        ("tldr 7d", timedelta(days=7)),
        ("tldr 168h", timedelta(days=7)),
    ],
)
def test_valid(text, window):
    assert p(text) == TldrCommand(window)


@pytest.mark.parametrize(
    "text",
    [
        "tldr 0h",
        "tldr 8d",
        "/tldr 169h",
        "tldr 200",
        "tldr 3m",
        "tldr 1h 2h",
        "tldr 小明 3m",
        "tldr 1h 小明 2h",
    ],
)
def test_invalid(text):
    assert isinstance(p(text), InvalidCommand)


@pytest.mark.parametrize(
    ("text", "person", "window"),
    [
        ("tldr 小明", "小明", DEFAULT),
        ("tldr @小明", "@小明", DEFAULT),
        ("tldr 小明 6h", "小明", timedelta(hours=6)),
        ("tldr 6h 小明", "小明", timedelta(hours=6)),
        ("tldr @Mary Chen 2d", "@Mary Chen", timedelta(days=2)),
        ("tldr 我覺得太長", "我覺得太長", DEFAULT),
        ("tldr 小明 2號", "小明 2號", DEFAULT),
    ],
)
def test_person(text, person, window):
    assert p(text) == TldrCommand(window, person)


def test_describe_window():
    assert describe_window(timedelta(hours=3)) == "3 小時"
    assert describe_window(timedelta(days=2)) == "2 天"
    assert describe_window(timedelta(hours=48)) == "2 天"
