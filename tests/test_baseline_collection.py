from media_omega.baseline_collection import collect_creator_baseline

OBSERVED = "2026-10-07T12:00:00+00:00"
PUBLISHED = "2026-10-07T02:00:00+00:00"


class Transport:
    def __init__(self, ids, stats):
        self.ids = ids
        self.stats = stats
        self.calls = []

    def channel_recent_video_ids(self, creator_id):
        return list(self.ids)

    def video_details(self, ids):
        self.calls.append(list(ids))
        return {
            x: {
                "views": self.stats[x],
                "published_at": PUBLISHED,
                "observed_at": OBSERVED,
            }
            for x in ids if x in self.stats
        }


def test_collection_excludes_target_to_avoid_self_contamination():
    t = Transport(["target", "a", "b", "c"], {"target": 999999, "a": 900, "b": 1000, "c": 1100})
    result = collect_creator_baseline(t, "creator", "target", minimum_samples=3)
    assert result.status == "READY"
    assert result.excluded_target is True
    assert result.baseline.median_views_per_hour == 100.0
    assert set(result.source_observed_at) == {OBSERVED}
    assert all(ref.endswith(f"@{OBSERVED}") for ref in result.source_refs)


def test_collection_fails_closed_on_too_little_history():
    t = Transport(["target", "a"], {"target": 50000, "a": 1000})
    result = collect_creator_baseline(t, "creator", "target", minimum_samples=3)
    assert result.status == "INSUFFICIENT_HISTORY"
    assert result.baseline is None


def test_collection_batches_large_channel_history():
    ids = [str(i) for i in range(120)]
    t = Transport(ids, {x: int(x) for x in ids})
    result = collect_creator_baseline(t, "creator", minimum_samples=3)
    assert [len(x) for x in t.calls] == [50, 50, 20]
    assert result.status == "READY"
