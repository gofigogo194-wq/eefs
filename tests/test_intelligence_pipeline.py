from media_omega.baseline_cache import CreatorBaselineCache
from media_omega.intelligence_pipeline import evaluate_content, rank_signals
from media_omega.observations import ContentObservation


def obs(cid, creator, hour, views):
    return ContentObservation(
        "youtube", cid, creator, "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hour:02d}:00:00+00:00", views, 1,
        f"api://youtube/{cid}/{hour}",
    )


class Transport:
    def channel_recent_video_ids(self, creator_id):
        return [f"{creator_id}-old1", f"{creator_id}-old2", f"{creator_id}-old3"]

    def video_statistics(self, ids):
        return {x: 1000 for x in ids}


def test_pipeline_combines_creator_breakout_and_momentum():
    cache = CreatorBaselineCache(Transport())
    history = [obs("target", "c", 1, 1000), obs("target", "c", 2, 2000), obs("target", "c", 3, 5000)]
    signal = evaluate_content(history, cache)
    assert signal.status == "READY"
    assert signal.relative_creator_performance == 5.0
    assert signal.acceleration_ratio == 3.0
    assert signal.score > 0


def test_pipeline_fails_closed_without_creator_history():
    class Sparse(Transport):
        def channel_recent_video_ids(self, creator_id):
            return [f"{creator_id}-old1"]
    signal = evaluate_content(
        [obs("target", "c", 1, 100), obs("target", "c", 2, 200), obs("target", "c", 3, 400)],
        CreatorBaselineCache(Sparse()),
    )
    assert signal.status == "INSUFFICIENT_CREATOR_HISTORY"
    assert signal.score == 0.0


def test_signal_ranking_is_deterministic():
    cache = CreatorBaselineCache(Transport())
    fast = evaluate_content([obs("fast", "a", 1, 1000), obs("fast", "a", 2, 2000), obs("fast", "a", 3, 6000)], cache)
    slow = evaluate_content([obs("slow", "b", 1, 1000), obs("slow", "b", 2, 1500), obs("slow", "b", 3, 2100)], cache)
    assert [x.content_id for x in rank_signals([slow, fast])] == ["fast", "slow"]


def test_near_zero_previous_velocity_cannot_explode_score():
    cache = CreatorBaselineCache(Transport())
    signal = evaluate_content(
        [obs("edge", "c", 1, 1000), obs("edge", "c", 2, 1000), obs("edge", "c", 3, 1001)],
        cache,
    )
    assert signal.acceleration_ratio > 1000000
    assert signal.score < 20
    assert signal.version == "intelligence_pipeline.v2"
