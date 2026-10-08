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
            x: {
                "views": 1000,
                "published_at": PUBLISHED,
                "observed_at": OBSERVED,
            }
            for x in ids
        }


def test_same_creator_target_key_fetches_once():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    first = cache.get("creator", "creator-target")
    second = cache.get("creator", "creator-target")
    assert first is second
    assert t.history_calls == ["creator"]
    assert cache.size == 1
    assert set(first.source_observed_at) == {OBSERVED}
    assert all(ref.endswith(f"@{OBSERVED}") for ref in first.source_refs)


def test_target_is_excluded_from_creator_baseline():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    result = cache.get("creator", "creator-target")
    assert result.excluded_target is True
    assert result.requested_ids == 3
    assert result.returned_stats == 3


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


def test_same_creator_different_targets_reuse_one_raw_history_fetch():
    t = CountingTransport()
    cache = CreatorBaselineCache(t)
    first = cache.get("creator", "creator-target")
    second = cache.get("creator", "creator-a")
    assert first.status == "READY"
    assert second.status == "READY"
    assert t.history_calls == ["creator"]
    assert len(t.details_calls) == 1
    assert cache.size == 2


def test_large_creator_history_is_batched_by_transport_limit():
    class LargeTransport(CountingTransport):
        def channel_recent_video_ids(self, creator_id):
            self.history_calls.append(creator_id)
            return [str(i) for i in range(120)]

    t = LargeTransport()
    result = CreatorBaselineCache(t).get("creator")
    assert [len(batch) for batch in t.details_calls] == [50, 50, 20]
    assert result.status == "READY"
    assert result.requested_ids == 120
