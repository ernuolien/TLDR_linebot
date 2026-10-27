import pytest

from tldr_linebot.bot import (
    DIRECT_CHAT_REPLY,
    EMPTY_REPLY,
    FAILURE_REPLY,
    JOIN_NOTICE,
    UNKNOWN_NAME,
    Bot,
    IncomingMessage,
)
from tldr_linebot.llm import SummarizeError
from tldr_linebot.store import Store

NOW = 1_767_225_600.0  # 2026-01-01 00:00 UTC
HOUR_MS = 3_600_000


class FakeMessenger:
    def __init__(self):
        self.replies: list[tuple[str, str]] = []
        self.name_lookups = 0
        self.names = {"u1": "小明", "u2": "小華", "u3": "阿明", "u4": "小明明"}

    async def reply(self, reply_token, text):
        self.replies.append((reply_token, text))

    async def display_name(self, chat_id, is_room, user_id):
        self.name_lookups += 1
        return self.names.get(user_id)


class FakeSummarizer:
    def __init__(self, result="摘要結果"):
        self.result = result
        self.prompts: list[str] = []

    async def summarize(self, system, user):
        self.prompts.append(user)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def env(settings):
    store = Store(":memory:")
    messenger = FakeMessenger()
    summarizer = FakeSummarizer()
    clock = Clock()
    bot = Bot(settings, store, messenger, summarizer, clock=clock)
    return bot, store, messenger, summarizer, clock


def msg(
    text, *, chat="g1", user="u1", ts_ms=int(NOW * 1000), is_text=True, token="rt", mentions=()
):
    return IncomingMessage(
        chat_id=chat,
        is_room=False,
        user_id=user,
        text=text,
        is_text=is_text,
        ts_ms=ts_ms,
        reply_token=token,
        mentions=mentions,
    )


async def test_stores_messages_with_names_and_caches_lookups(env):
    bot, store, messenger, _, _ = env
    await bot.on_message(msg("hi"))
    await bot.on_message(msg("again"))
    await bot.on_message(msg("[貼圖]", is_text=False))

    messages, _ = store.since("g1", 0, 10)
    assert [(m.name, m.text) for m in messages] == [
        ("小明", "hi"),
        ("小明", "again"),
        ("小明", "[貼圖]"),
    ]
    assert messenger.name_lookups == 1
    assert messenger.replies == []


async def test_unknown_user_name(env):
    bot, store, *_ = env
    await bot.on_message(msg("hi", user="ghost"))
    await bot.on_message(msg("hi", user=None))
    assert {m.name for m in store.since("g1", 0, 10)[0]} == {UNKNOWN_NAME}


async def test_command_not_stored(env):
    bot, store, *_ = env
    await bot.on_message(msg("/tldr"))
    assert store.since("g1", 0, 10)[1] == 0


async def test_tldr_summarizes_only_window(env):
    bot, _, messenger, summarizer, _ = env
    now_ms = int(NOW * 1000)
    await bot.on_message(msg("太舊了", ts_ms=now_ms - 4 * HOUR_MS))
    await bot.on_message(msg("晚餐吃什麼", ts_ms=now_ms - 1 * HOUR_MS))

    await bot.on_message(msg("/tldr", token="t1"))

    assert messenger.replies == [("t1", "摘要結果")]
    assert "晚餐吃什麼" in summarizer.prompts[0]
    assert "太舊了" not in summarizer.prompts[0]


async def test_tldr_custom_window(env):
    bot, _, _, summarizer, _ = env
    await bot.on_message(msg("兩天前", ts_ms=int(NOW * 1000) - 47 * HOUR_MS))
    await bot.on_message(msg("tldr 2d"))
    assert "兩天前" in summarizer.prompts[0]


async def test_tldr_with_no_messages(env):
    bot, _, messenger, summarizer, _ = env
    await bot.on_message(msg("/tldr"))
    assert messenger.replies == [("rt", EMPTY_REPLY)]
    assert summarizer.prompts == []


async def test_invalid_command_replies_usage(env):
    bot, _, messenger, _, _ = env
    await bot.on_message(msg("tldr 9d"))
    assert "用法" in messenger.replies[0][1]


async def test_cooldown(env):
    bot, _, messenger, _, clock = env
    await bot.on_message(msg("hi"))
    await bot.on_message(msg("/tldr", token="a"))
    clock.now += 30
    await bot.on_message(msg("/tldr", token="b"))
    clock.now += 31
    await bot.on_message(msg("/tldr", token="c"))

    assert messenger.replies[0] == ("a", "摘要結果")
    assert messenger.replies[1][0] == "b" and "稍候" in messenger.replies[1][1]
    assert messenger.replies[2] == ("c", "摘要結果")


async def test_cooldown_is_per_chat(env):
    bot, _, messenger, _, _ = env
    await bot.on_message(msg("hi", chat="g1"))
    await bot.on_message(msg("hi", chat="g2"))
    await bot.on_message(msg("/tldr", chat="g1"))
    await bot.on_message(msg("/tldr", chat="g2"))
    assert [text for _, text in messenger.replies] == ["摘要結果", "摘要結果"]


async def test_truncation_notice(env, settings):
    bot, _, messenger, _, _ = env
    settings.max_messages = 2
    for i in range(3):
        await bot.on_message(msg(f"m{i}", ts_ms=int(NOW * 1000) - 10 + i))
    await bot.on_message(msg("/tldr"))
    assert messenger.replies[0][1].startswith("（訊息過多，僅摘要最近 2 則，共 3 則）")


async def test_summarizer_failure(env):
    bot, _, messenger, summarizer, _ = env
    summarizer.result = SummarizeError("boom")
    await bot.on_message(msg("hi"))
    await bot.on_message(msg("/tldr"))
    assert messenger.replies == [("rt", FAILURE_REPLY)]


async def test_direct_chat_gets_usage_and_is_not_stored(env):
    bot, store, messenger, _, _ = env
    await bot.on_message(msg("hello", chat=None))
    await bot.on_message(msg("/tldr", chat=None))
    assert messenger.replies == [("rt", DIRECT_CHAT_REPLY)] * 2
    assert store.since("g1", 0, 10)[1] == 0


async def test_join_and_leave(env):
    bot, store, messenger, _, _ = env
    await bot.on_join("jt")
    await bot.on_message(msg("hi"))
    bot.on_leave("g1")
    assert messenger.replies == [("jt", JOIN_NOTICE)]
    assert store.since("g1", 0, 10)[1] == 0


async def test_purge_expired(env):
    bot, store, *_ = env
    now_ms = int(NOW * 1000)
    await bot.on_message(msg("old", ts_ms=now_ms - 8 * 24 * HOUR_MS))
    await bot.on_message(msg("new", ts_ms=now_ms - HOUR_MS))
    assert bot.purge_expired() == 1
    assert [m.text for m in store.since("g1", 0, 10)[0]] == ["new"]


async def _chat(bot):
    now_ms = int(NOW * 1000)
    await bot.on_message(msg("週五要不要聚餐", user="u1", ts_ms=now_ms - 30 * 60_000))
    await bot.on_message(msg("好啊我可以訂位", user="u2", ts_ms=now_ms - 20 * 60_000))
    await bot.on_message(msg("那我負責找地點", user="u1", ts_ms=now_ms - 10 * 60_000))


async def test_person_summary_by_name(env):
    bot, _, messenger, summarizer, _ = env
    await _chat(bot)
    await bot.on_message(msg("tldr 小明", user="u2"))

    reply = messenger.replies[0][1]
    assert reply.startswith("小明（最近 3 小時，2 則）\n")
    prompt = summarizer.prompts[0]
    assert prompt.startswith("目標成員：小明")
    assert "▶[" in prompt and "小明: 週五要不要聚餐" in prompt
    assert "▶[01/01 07:40] 小華" not in prompt  # other people stay as context, unmarked
    assert "小華: 好啊我可以訂位" in prompt


async def test_person_partial_name_and_duration_first(env):
    bot, _, messenger, _, _ = env
    await _chat(bot)
    await bot.on_message(msg("tldr 6h 華"))
    assert messenger.replies[0][1].startswith("小華（最近 6 小時，1 則）")


async def test_exact_name_beats_partial(env):
    bot, _, messenger, _, _ = env
    await _chat(bot)
    await bot.on_message(msg("嗨", user="u4"))  # 小明明
    await bot.on_message(msg("tldr 小明"))
    assert messenger.replies[0][1].startswith("小明（")


async def test_ambiguous_name(env):
    bot, _, messenger, summarizer, _ = env
    await _chat(bot)
    await bot.on_message(msg("tldr 小"))
    assert messenger.replies[0][1].startswith("找到多位：小明、小華")
    assert summarizer.prompts == []


async def test_unknown_name_is_ordinary_chat(env):
    bot, store, messenger, summarizer, _ = env
    await _chat(bot)
    await bot.on_message(msg("tldr 我覺得太長"))
    assert messenger.replies == []
    assert summarizer.prompts == []
    assert store.since("g1", 0, 10)[0][-1].text == "tldr 我覺得太長"
    # and it did not use up the cooldown
    await bot.on_message(msg("tldr"))
    assert messenger.replies == [("rt", "摘要結果")]


async def test_person_by_mention(env):
    bot, _, messenger, _, _ = env
    await _chat(bot)
    await bot.on_message(msg("tldr @隨便打的名字", mentions=("u2",)))
    assert messenger.replies[0][1].startswith("小華（最近 3 小時，1 則）")


async def test_mention_of_someone_who_did_not_speak(env):
    bot, _, messenger, summarizer, _ = env
    await _chat(bot)
    await bot.on_message(msg("tldr @阿明", mentions=("u3",)))
    assert messenger.replies == [("rt", "最近 3 小時內沒有 阿明 的發言。")]
    assert summarizer.prompts == []


async def test_person_outside_window_is_unknown(env):
    bot, _, messenger, _, _ = env
    await bot.on_message(msg("很久以前", user="u2", ts_ms=int(NOW * 1000) - 5 * HOUR_MS))
    await bot.on_message(msg("最近", user="u1"))
    await bot.on_message(msg("tldr 小華"))
    assert messenger.replies == []  # 小華 hasn't spoken in the last 3 hours
    await bot.on_message(msg("tldr 小華 6h", token="t2"))
    assert messenger.replies[0][1].startswith("小華（最近 6 小時，1 則）")


async def test_question_looks_back_over_retention(env):
    bot, _, messenger, summarizer, _ = env
    now_ms = int(NOW * 1000)
    await bot.on_message(msg("媽媽下週一住院，要帶健保卡", ts_ms=now_ms - 5 * 24 * HOUR_MS))
    await bot.on_message(msg("晚餐吃什麼", user="u2", ts_ms=now_ms - HOUR_MS))

    await bot.on_message(msg("tldr ? 幫我整理住院有關的事情", token="q"))

    assert messenger.replies == [("q", "🔍 幫我整理住院有關的事情（最近 7 天）\n摘要結果")]
    prompt = summarizer.prompts[0]
    assert prompt.startswith("<request>\n幫我整理住院有關的事情\n</request>")
    assert "媽媽下週一住院" in prompt and "晚餐吃什麼" in prompt


async def test_question_with_window(env):
    bot, store, messenger, summarizer, _ = env
    now_ms = int(NOW * 1000)
    await bot.on_message(msg("太舊了", ts_ms=now_ms - 3 * 24 * HOUR_MS))
    await bot.on_message(msg("住院手續", ts_ms=now_ms - HOUR_MS))
    await bot.on_message(msg("tldr 問 住院 2d"))

    assert messenger.replies[0][1].startswith("🔍 住院（最近 2 天）\n")
    assert "太舊了" not in summarizer.prompts[0]
    assert len(store.since("g1", 0, 10)[0]) == 2  # the question itself is not stored
