from media_omega.baseline_cache import CreatorBaselineCache


OBSERVED = "2026-10-07T12:00:00+00:00"
PUBLISHED = "2026-10-07T02:00:00+00:00"


class CountingTransport:
    def __init__(self):
        self.history_calls = []
        self.details_calls = []

    def channel_recent_video_ids(self, creator_id):
        self.history_calls.append(creator_id)
        return [
            f"{creator_id}-target",
            f"{creator_id}-a",
            f"{creator_id}-b",
            f"{creator_id}-c",
        ]

    def video_details(self, ids):
        self.details_calls.append(tuple(ids))
        return {
            x: {"views": 1000, "published_at": PUBLISHED}
            for x in ids
        }


def test_same_creator_target_key_fetches_once():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    first = cache.get("creator", "creator-target", OBSERVED)
    second = cache.get("creator", "creator-target", OBSERVED)
    assert first is second
    assert t.history_calls == ["creator"]
    assert cache.size == 1


def test_different_creators_fetch_independently():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    cache.get("a", "a-target", OBSERVED)
    cache.get("b", "b-target", OBSERVED)
    assert t.history_calls == ["a", "b"]
    assert cache.size == 2


def test_insufficient_history_is_cached_too():
    class SparseTransport(CountingTransport):
        def channel_recent_video_ids(self, creator_id):
            self.history_calls.append(creator_id)
            return [f"{creator_id}-target", f"{creator_id}-a"]

    t = SparseTransport()
    cache = CreatorBaselineCache(t, minimum_samples=3)
    assert cache.get("c", "c-target", OBSERVED).status == "INSUFFICIENT_HISTORY"
    assert cache.get("c", "c-target", OBSERVED).status == "INSUFFICIENT_HISTORY"
    assert t.history_calls == ["c"]


def test_same_creator_different_targets_reuse_one_raw_history_fetch():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    first = cache.get("creator", "creator-target", OBSERVED)
    second = cache.get("creator", "creator-a", OBSERVED)
    assert first.status == "READY"
    assert second.status == "READY"
    assert t.history_calls == ["creator"]
    assert len(t.details_calls) == 1
    assert cache.size == 2


def test_same_instant_different_offset_reuses_derived_result():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    a = cache.get("creator", "creator-target", "2026-10-07T12:00:00+00:00")
    b = cache.get("creator", "creator-target", "2026-10-07T19:00:00+07:00")
    assert a is b
    assert cache.size == 1
