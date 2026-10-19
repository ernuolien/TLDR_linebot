"""Parsing of the `tldr [N(h|d)]` command (a leading slash is optional)."""

import re
from dataclasses import dataclass
from datetime import timedelta

_COMMAND = re.compile(r"^/?tldr(?:\s+(\S+))?$", re.IGNORECASE)
_DURATION = re.compile(r"^(\d+)([hd])$", re.IGNORECASE)

USAGE = (
    "用法：\ntldr　摘要最近 12 小時\ntldr 3h　摘要最近 3 小時\ntldr 2d　摘要最近 2 天（最多 7 天）"
)


@dataclass(frozen=True)
class TldrCommand:
    window: timedelta


@dataclass(frozen=True)
class InvalidCommand:
    reason: str


def parse(text: str, default: timedelta, maximum: timedelta) -> TldrCommand | InvalidCommand | None:
    """Return None if `text` is ordinary chat rather than a tldr command.

    Only `tldr` alone or followed by something that looks like a duration
    (`tldr 3h`) counts, so chat such as "tldr 我覺得太長" is left alone."""
    match = _COMMAND.match(text.strip())
    if not match:
        return None
    arg = match.group(1)
    if arg is None:
        return TldrCommand(default)
    if not arg[0].isdigit():
        return None

    duration = _DURATION.match(arg)
    if not duration:
        return InvalidCommand(USAGE)
    amount, unit = int(duration.group(1)), duration.group(2).lower()
    window = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
    if window <= timedelta(0) or window > maximum:
        return InvalidCommand(f"時間範圍需介於 1h 到 {maximum.days}d 之間。\n\n{USAGE}")
    return TldrCommand(window)
