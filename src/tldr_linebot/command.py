"""Parsing of the `/tldr [N(h|d)]` command."""

import re
from dataclasses import dataclass
from datetime import timedelta

_COMMAND = re.compile(r"^/tldr(?:\s+(\S+))?\s*$", re.IGNORECASE)
_DURATION = re.compile(r"^(\d+)([hd])$", re.IGNORECASE)

USAGE = (
    "用法：\n"
    "/tldr　摘要最近 12 小時\n"
    "/tldr 3h　摘要最近 3 小時\n"
    "/tldr 2d　摘要最近 2 天（最多 7 天）"
)


@dataclass(frozen=True)
class TldrCommand:
    window: timedelta


@dataclass(frozen=True)
class InvalidCommand:
    reason: str


def parse(text: str, default: timedelta, maximum: timedelta) -> TldrCommand | InvalidCommand | None:
    """Return None if `text` is not a /tldr command at all."""
    stripped = text.strip()
    if not stripped.lower().startswith("/tldr"):
        return None
    match = _COMMAND.match(stripped)
    if not match:
        return InvalidCommand(USAGE)
    arg = match.group(1)
    if arg is None:
        return TldrCommand(default)

    duration = _DURATION.match(arg)
    if not duration:
        return InvalidCommand(USAGE)
    amount, unit = int(duration.group(1)), duration.group(2).lower()
    window = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
    if window <= timedelta(0) or window > maximum:
        return InvalidCommand(f"時間範圍需介於 1h 到 {maximum.days}d 之間。\n\n{USAGE}")
    return TldrCommand(window)
