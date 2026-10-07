import pytest

from media_omega.cohort import PeerCohortPolicy, build_peer_cohort
from media_omega.observations import ContentObservation


def obs(
    content_id,
    *,
    query="ambient sleep",
    hours=10,
    platform="youtube",
    content_format="unknown",
):
    return ContentObservation(
        platform,
        content_id,
        "creator",
        "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hours:02d}:00:00+00:00",
        1000,
        1000,
        f"fixture://{content_id}",
        query,
        content_format,
    )


def test_policy_requires_explicit_nontrivial_age_comparability():
    with pytest.raises(ValueError):
        PeerCohortPolicy(max_age_ratio=0.9).validate()


def test_cohort_requires_query_provenance():
    result = build_peer_cohort(
        obs("candidate", query=""),
        [obs("p1")],
        PeerCohortPolicy(max_age_ratio=2.0),
    )
    assert result.status == "INSUFFICIENT_QUERY_PROVENANCE"
    assert result.peer_content_ids == ()


def test_cohort_filters_platform_query_and_age_with_explicit_policy():
    candidate = obs("candidate", hours=10)
    peers = [
        obs("good-1", hours=8),
        obs("good-2", hours=12),
        obs("good-3", query="  AMBIENT   SLEEP ", hours=15),
        obs("wrong-query", query="robotics", hours=10),
        obs("wrong-platform", platform="instagram", hours=10),
        obs("too-old", hours=23),
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
