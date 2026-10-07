from media_omega.baseline_cache import CreatorBaselineCache


class CountingTransport:
    def __init__(self):
        self.history_calls = []
        self.stats_calls = []

    def channel_recent_video_ids(self, creator_id):
        self.history_calls.append(creator_id)
        return [f"{creator_id}-target", f"{creator_id}-a", f"{creator_id}-b", f"{creator_id}-c"]

    def video_statistics(self, ids):
        self.stats_calls.append(tuple(ids))
        return {x: 1000 for x in ids}


def test_same_creator_target_key_fetches_once():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    first = cache.get("creator", "creator-target")
    second = cache.get("creator", "creator-target")
    assert first is second
    assert t.history_calls == ["creator"]
    assert cache.size == 1


def test_different_creators_fetch_independently():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    cache.get("a", "a-target")
    cache.get("b", "b-target")
    assert t.history_calls == ["a", "b"]
    assert cache.size == 2


def test_insufficient_history_is_cached_too():
    class SparseTransport(CountingTransport):
        def channel_recent_video_ids(self, creator_id):
            self.history_calls.append(creator_id)
            return [f"{creator_id}-target", f"{creator_id}-a"]

    t = SparseTransport()
    cache = CreatorBaselineCache(t, minimum_samples=3)
    assert cache.get("c", "c-target").status == "INSUFFICIENT_HISTORY"
    assert cache.get("c", "c-target").status == "INSUFFICIENT_HISTORY"
    assert t.history_calls == ["c"]
