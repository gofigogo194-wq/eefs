from media_omega.baseline_cache import CreatorBaselineCache
from media_omega.cohort import PeerCohortPolicy
from media_omega.intelligence_pipeline import IntelligencePolicy, evaluate_content, rank_signals
from media_omega.observations import ContentObservation


def obs(cid, creator, hour, views, query="", content_format="unknown"):
    return ContentObservation(
        "youtube", cid, creator, "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hour:02d}:00:00+00:00", views, 0,
        f"api://youtube/{cid}/{hour}", query, content_format,
    )


class Transport:
    def __init__(self, observed_at="2026-10-07T03:00:00+00:00"):
        self.history_calls = 0
        self.details_calls = 0
        self.observed_at = observed_at

    def channel_recent_video_ids(self, creator_id):
        self.history_calls += 1
        return [f"{creator_id}-old1", f"{creator_id}-old2", f"{creator_id}-old3"]

    def video_details(self, ids):
        self.details_calls += 1
        return {
            x: {
                "views": 1000,
                "published_at": "2026-10-07T00:00:00+00:00",
                "observed_at": self.observed_at,
            } for x in ids
        }


def test_pipeline_combines_age_normalized_creator_breakout_and_momentum():
    signal = evaluate_content(
        [obs("target", "c", 1, 1000), obs("target", "c", 2, 2000), obs("target", "c", 3, 5000)],
        CreatorBaselineCache(Transport()),
    )
    assert signal.status == "READY"
    assert signal.relative_creator_performance == 5.0
    assert signal.acceleration_ratio == 3.0
    assert signal.score > 0
    assert signal.baseline_max_skew_seconds == 0.0


def test_pipeline_fails_closed_without_creator_history():
    class Sparse(Transport):
        def channel_recent_video_ids(self, creator_id):
            self.history_calls += 1
            return [f"{creator_id}-old1"]

    signal = evaluate_content(
        [obs("target", "c", 1, 100), obs("target", "c", 2, 200), obs("target", "c", 3, 400)],
        CreatorBaselineCache(Sparse()),
    )
    assert signal.status == "INSUFFICIENT_CREATOR_HISTORY"
    assert signal.score == 0.0


def test_stale_live_creator_baseline_cannot_score_historical_target_snapshot():
    signal = evaluate_content(
        [obs("target", "c", 1, 1000), obs("target", "c", 2, 2000), obs("target", "c", 3, 5000)],
        CreatorBaselineCache(Transport("2026-10-07T05:00:00+00:00")),
        policy=IntelligencePolicy(max_baseline_skew_seconds=60),
    )
    assert signal.status == "STALE_CREATOR_BASELINE"
    assert signal.score == 0.0
    assert signal.baseline_max_skew_seconds == 7200.0


def test_intelligence_policy_rejects_invalid_skew():
    try:
        IntelligencePolicy(max_baseline_skew_seconds=0).validate()
    except ValueError as exc:
        assert "max_baseline_skew_seconds" in str(exc)
    else:
        raise AssertionError("zero baseline skew must be rejected")


def test_signal_ranking_is_deterministic():
    cache = CreatorBaselineCache(Transport())
    fast = evaluate_content([obs("fast", "a", 1, 1000), obs("fast", "a", 2, 2000), obs("fast", "a", 3, 6000)], cache)
    slow = evaluate_content([obs("slow", "b", 1, 1000), obs("slow", "b", 2, 1500), obs("slow", "b", 3, 2100)], cache)
    assert [x.content_id for x in rank_signals([slow, fast])] == ["fast", "slow"]


def test_near_zero_previous_velocity_cannot_explode_score():
    signal = evaluate_content(
        [obs("edge", "c", 1, 1000), obs("edge", "c", 2, 1000), obs("edge", "c", 3, 1001)],
        CreatorBaselineCache(Transport()),
    )
    assert signal.acceleration_ratio == 1.0
    assert signal.score < 1.0


def test_bad_temporal_history_fails_before_creator_api_work():
    transport = Transport()
    history = [
        ContentObservation("youtube", "target", "c", "2026-10-07T00:00:00+00:00", "2026-10-07T01:00:00+00:00", 100, 0, "fixture://1"),
        ContentObservation("youtube", "target", "c", "2026-10-07T00:00:00+00:00", "2026-10-07T01:00:10+00:00", 110, 0, "fixture://2"),
        ContentObservation("youtube", "target", "c", "2026-10-07T00:00:00+00:00", "2026-10-07T01:00:20+00:00", 120, 0, "fixture://3"),
    ]
    try:
        evaluate_content(history, CreatorBaselineCache(transport))
    except ValueError as exc:
        assert "interval is too short" in str(exc)
    else:
        raise AssertionError("unreliable temporal evidence must fail closed")
    assert transport.history_calls == 0
    assert transport.details_calls == 0


def test_pipeline_reports_comparable_peer_cohort_without_changing_score_formula():
    history = [
        obs("target", "c", 1, 1000, "ambient sleep", "long-form"),
        obs("target", "c", 2, 2000, "ambient sleep", "long-form"),
        obs("target", "c", 3, 5000, "ambient sleep", "long-form"),
    ]
    peers = [
        obs("p1", "x", 2, 1000, "ambient sleep", "long-form"),
        obs("p2", "y", 3, 1200, "ambient sleep", "long-form"),
        obs("p3", "z", 4, 900, "ambient sleep", "long-form"),
    ]
    signal = evaluate_content(
        history,
        CreatorBaselineCache(Transport()),
        peers,
        PeerCohortPolicy(
            max_age_ratio=2.0,
            minimum_peers=3,
            max_observation_skew_seconds=7200,
        ),
    )
    assert signal.status == "READY"
    assert signal.peer_cohort_status == "READY"
    assert signal.peer_count == 3
