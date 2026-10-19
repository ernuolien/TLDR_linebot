from tldr_linebot.store import Store


def test_since_returns_newest_within_limit_oldest_first():
    store = Store(":memory:")
    for i in range(5):
        store.add("g1", "u", "A", f"m{i}", 1000 + i)
    store.add("g2", "u", "A", "other", 1002)

    messages, total = store.since("g1", 1001, limit=3)

    assert total == 4
    assert [m.text for m in messages] == ["m2", "m3", "m4"]


def test_delete_older_than_and_delete_chat():
    store = Store(":memory:")
    store.add("g1", "u", "A", "old", 100)
    store.add("g1", "u", "A", "new", 200)
    store.add("g2", "u", "A", "x", 200)

    assert store.delete_older_than(150) == 1
    assert store.delete_chat("g1") == 1
    assert store.since("g2", 0, 10)[1] == 1
