"""Parsing of the `tldr [person] [N(h|d)]` and `tldr ? <question> [N(h|d)]` commands
(a leading slash is optional)."""

import re
from dataclasses import dataclass
from datetime import timedelta

_COMMAND = re.compile(r"^/?tldr(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
_DURATION_LIKE = re.compile(r"^\d+[a-z]*$", re.IGNORECASE)
_DURATION = re.compile(r"^(\d+)([hd])$", re.IGNORECASE)
_QUESTION = re.compile(r"^(?:[?？]|問\s)\s*(.*)$", re.DOTALL)

USAGE = (
    "用法：\n"
    "tldr　摘要最近 3 小時\n"
    "tldr 6h／tldr 2d　指定時間（最多 7 天）\n"
    "tldr 小明／tldr @小明　統整某人說的話\n"
    "tldr 小明 6h　兩者可以合用\n"
    "tldr ? 住院的事　從最近 7 天的對話中整理某件事（也可以打「tldr 問 …」）"
)


@dataclass(frozen=True)
class TldrCommand:
    window: timedelta
    person: str | None = None  # raw name query as typed, e.g. "小明" or "@小明"
    question: str | None = None  # free-form request, e.g. "幫我整理住院有關的事情"


@dataclass(frozen=True)
class InvalidCommand:
    reason: str


def parse(text: str, default: timedelta, maximum: timedelta) -> TldrCommand | InvalidCommand | None:
    """Return None if `text` is not a tldr command at all.

    A duration (`3h`, `2d`) may come first or last; any remaining words are the
    person to summarize. Whether that person exists is decided by the caller,
    which treats an unknown name as ordinary chat."""
    match = _COMMAND.match(text.strip())
    if not match:
        return None
    rest = match.group(1) or ""
    question = _QUESTION.match(rest)
    if question:
        return _parse_question(question.group(1), maximum)
    words = rest.split()
    if not words:
        return TldrCommand(default)

    duration_word = None
    if _DURATION_LIKE.match(words[-1]):
        duration_word = words.pop()
    elif _DURATION_LIKE.match(words[0]):
        duration_word = words.pop(0)
    if words and (_DURATION_LIKE.match(words[0]) or _DURATION_LIKE.match(words[-1])):
        return InvalidCommand(USAGE)  # more than one duration

    window = default
    if duration_word is not None:
        window = _window(duration_word, maximum)
        if isinstance(window, InvalidCommand):
            return window

    return TldrCommand(window, " ".join(words) or None)


def _parse_question(text: str, maximum: timedelta) -> TldrCommand | InvalidCommand:
    """A question looks back over all retained messages unless it ends with a duration.
    Only a well-formed duration (`2d`) is taken off the end, so a question that happens
    to end in a number stays intact."""
    words = text.split()
    window: timedelta | InvalidCommand = maximum
    if len(words) > 1 and _DURATION.match(words[-1]):
        window = _window(words.pop(), maximum)
        if isinstance(window, InvalidCommand):
            return window
    if not words:
        return InvalidCommand(USAGE)
    return TldrCommand(window, question=" ".join(words))


def _window(word: str, maximum: timedelta) -> timedelta | InvalidCommand:
    duration = _DURATION.match(word)
    if not duration:
        return InvalidCommand(USAGE)
    amount, unit = int(duration.group(1)), duration.group(2).lower()
    window = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
    if window <= timedelta(0) or window > maximum:
        return InvalidCommand(f"時間範圍需介於 1h 到 {maximum.days}d 之間。\n\n{USAGE}")
    return window


def describe_window(window: timedelta) -> str:
    hours = int(window.total_seconds() // 3600)
    if hours % 24 == 0:
        return f"{hours // 24} 天"
    return f"{hours} 小時"
