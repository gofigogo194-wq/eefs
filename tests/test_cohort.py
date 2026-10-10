from datetime import datetime, timedelta, timezone

import pytest

from media_omega.cohort import PeerCohortPolicy, build_peer_cohort
from media_omega.observations import ContentObservation


DEFAULT_OBSERVED = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def obs(
    content_id,
    *,
    query="ambient sleep",
    age_hours=10,
    observed_at=DEFAULT_OBSERVED,
    platform="youtube",
    content_format="unknown",
):
    published_at = observed_at - timedelta(hours=age_hours)
    return ContentObservation(
        platform,
        content_id,
        "creator",
        published_at.isoformat(),
        observed_at.isoformat(),
        1000,
        0,
        f"fixture://{content_id}",
        query,
        content_format,
    )


def test_policy_requires_explicit_valid_comparability_bounds():
    with pytest.raises(ValueError):
        PeerCohortPolicy(max_age_ratio=0.9).validate()
    with pytest.raises(ValueError):
        PeerCohortPolicy(
            max_age_ratio=2.0,
            max_observation_skew_seconds=-1,
        ).validate()


def test_cohort_requires_query_provenance():
    result = build_peer_cohort(
        obs("candidate", query=""),
        [obs("p1")],
        PeerCohortPolicy(max_age_ratio=2.0),
    )
    assert result.status == "INSUFFICIENT_QUERY_PROVENANCE"
    assert result.peer_content_ids == ()
    assert result.version == "peer_cohort.v2"


def test_cohort_filters_platform_query_and_age_with_explicit_policy():
    candidate = obs("candidate", age_hours=10)
    peers = [
        obs("good-1", age_hours=8),
        obs("good-2", age_hours=12),
        obs("good-3", query="  AMBIENT   SLEEP ", age_hours=15),
        obs("wrong-query", query="robotics", age_hours=10),
        obs("wrong-platform", platform="instagram", age_hours=10),
        obs("too-old", age_hours=23),
    ]
    result = build_peer_cohort(
        candidate,
        peers,
        PeerCohortPolicy(max_age_ratio=2.0, minimum_peers=3),
    )
    assert result.peer_content_ids == ("good-1", "good-2", "good-3")
    assert result.status == "READY_PARTIAL_FORMAT_UNKNOWN"
    assert result.excluded_query == 1
    assert result.excluded_platform == 1
    assert result.excluded_age == 1
    assert result.excluded_observation_skew == 0


def test_stale_peer_snapshot_is_excluded_even_when_content_age_matches():
    candidate = obs("candidate", age_hours=10)
    stale_time = DEFAULT_OBSERVED - timedelta(hours=2)
    peers = [
        obs("fresh-1", age_hours=10),
        obs("fresh-2", age_hours=10),
        obs("fresh-3", age_hours=10),
        obs("stale", age_hours=10, observed_at=stale_time),
    ]
    result = build_peer_cohort(
        candidate,
        peers,
        PeerCohortPolicy(
            max_age_ratio=2.0,
            minimum_peers=3,
            max_observation_skew_seconds=900,
        ),
    )
    assert result.peer_content_ids == ("fresh-1", "fresh-2", "fresh-3")
    assert result.excluded_observation_skew == 1


def test_known_format_must_match():
    candidate = obs("candidate", content_format="long-form")
    peers = [
        obs("a", content_format="long-form"),
        obs("b", content_format="short"),
        obs("c", content_format="long-form"),
        obs("d", content_format="long-form"),
    ]
    result = build_peer_cohort(
        candidate,
        peers,
        PeerCohortPolicy(max_age_ratio=2.0, minimum_peers=3),
    )
    assert result.status == "READY"
    assert result.peer_content_ids == ("a", "c", "d")
    assert result.excluded_format == 1
