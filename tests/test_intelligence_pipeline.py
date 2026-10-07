from media_omega.baseline_cache import CreatorBaselineCache
from media_omega.cohort import PeerCohortPolicy
from media_omega.intelligence_pipeline import evaluate_content, rank_signals
from media_omega.observations import ContentObservation


def obs(cid, creator, hour, views, query="", content_format="unknown"):
    return ContentObservation(
        "youtube",
        cid,
        creator,
        "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hour:02d}:00:00+00:00",
        views,
        1,
        f"api://youtube/{cid}/{hour}",
        query,
        content_format,
    )


class Transport:
    def __init__(self):
        self.history_calls = 0
        self.details_calls = 0

    def channel_recent_video_ids(self, creator_id):
        self.history_calls += 1
        return [
            f"{creator_id}-old1",
            f"{creator_id}-old2",
            f"{creator_id}-old3",
        ]

    def video_details(self, ids):
        self.details_calls += 1
        return {
            x: {
                "views": 1000,
                "published_at": "2026-10-07T00:00:00+00:00",
            }
            for x in ids
        }


def test_pipeline_combines_age_normalized_creator_breakout_and_momentum():
    cache = CreatorBaselineCache(Transport())
    history = [
        obs("target", "c", 1, 1000),
        obs("target", "c", 2, 2000),
        obs("target", "c", 3, 5000),
    ]
    signal = evaluate_content(history, cache)
    assert signal.status == "READY"
    assert signal.relative_creator_performance == 5.0
    assert signal.acceleration_ratio == 3.0
    assert signal.score > 0
    assert signal.version == "intelligence_pipeline.v4"


def test_pipeline_fails_closed_without_creator_history():
    class Sparse(Transport):
        def channel_recent_video_ids(self, creator_id):
            self.history_calls += 1
            return [f"{creator_id}-old1"]

    signal = evaluate_content(
        [
            obs("target", "c", 1, 100),
            obs("target", "c", 2, 200),
            obs("target", "c", 3, 400),
        ],
        CreatorBaselineCache(Sparse()),
    )
    assert signal.status == "INSUFFICIENT_CREATOR_HISTORY"
    assert signal.score == 0.0


def test_signal_ranking_is_deterministic():
    cache = CreatorBaselineCache(Transport())
    fast = evaluate_content(
        [obs("fast", "a", 1, 1000), obs("fast", "a", 2, 2000), obs("fast", "a", 3, 6000)],
        cache,
    )
    slow = evaluate_content(
        [obs("slow", "b", 1, 1000), obs("slow", "b", 2, 1500), obs("slow", "b", 3, 2100)],
        cache,
    )
    assert [x.content_id for x in rank_signals([slow, fast])] == ["fast", "slow"]


def test_near_zero_previous_velocity_cannot_explode_score():
    cache = CreatorBaselineCache(Transport())
    signal = evaluate_content(
        [obs("edge", "c", 1, 1000), obs("edge", "c", 2, 1000), obs("edge", "c", 3, 1001)],
        cache,
    )
    assert signal.acceleration_ratio == 1.0
    assert signal.score < 1.0


def test_bad_temporal_history_fails_before_creator_api_work():
    transport = Transport()
    cache = CreatorBaselineCache(transport)
    history = [
        ContentObservation(
            "youtube", "target", "c",
            "2026-10-07T00:00:00+00:00",
            "2026-10-07T01:00:00+00:00",
            100, 1, "fixture://1",
        ),
        ContentObservation(
            "youtube", "target", "c",
            "2026-10-07T00:00:00+00:00",
            "2026-10-07T01:00:10+00:00",
            110, 1, "fixture://2",
        ),
        ContentObservation(
            "youtube", "target", "c",
            "2026-10-07T00:00:00+00:00",
            "2026-10-07T01:00:20+00:00",
            120, 1, "fixture://3",
        ),
    ]
    try:
        evaluate_content(history, cache)
    except ValueError as exc:
        assert "interval is too short" in str(exc)
    else:
        raise AssertionError("unreliable temporal evidence must fail closed")
    assert transport.history_calls == 0
    assert transport.details_calls == 0


def test_pipeline_reports_comparable_peer_cohort_without_changing_score_formula():
    cache = CreatorBaselineCache(Transport())
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
        cache,
        peers,
        PeerCohortPolicy(max_age_ratio=2.0, minimum_peers=3),
    )
    assert signal.status == "READY"
    assert signal.peer_cohort_status == "READY"
    assert signal.peer_count == 3
    assert signal.version == "intelligence_pipeline.v4"
