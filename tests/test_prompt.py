from zoneinfo import ZoneInfo

from tldr_linebot.prompt import build_chat_log, build_user_prompt
from tldr_linebot.store import StoredMessage

TZ = ZoneInfo("Asia/Taipei")


def test_formats_in_local_time():
    # 2026-01-01 00:00 UTC == 08:00 in Taipei
    log, n = build_chat_log([StoredMessage("小明", "早安", 1767225600000)], TZ, 1000)
    assert log == "[01/01 08:00] 小明: 早安"
    assert n == 1


def test_keeps_newest_messages_within_budget():
    messages = [StoredMessage("A", f"msg{i}", 1767225600000 + i) for i in range(10)]
    log, n = build_chat_log(messages, TZ, max_chars=60)
    assert n == 2
    assert log.splitlines()[-1].endswith("msg9")


def test_user_prompt_wraps_chat():
    assert "<chat>\nlog\n</chat>" in build_user_prompt("log")
