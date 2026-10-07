import pytest

from media_omega.evidence import evidence_hash, record_evidence
from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation, detect_outlier


def obs(content_id, views, baseline=1000, hours=10, platform="youtube", evidence="fixture://x"):
    return ContentObservation(
        platform=platform,
        content_id=content_id,
        creator_id="creator",
        published_at="2026-10-01T00:00:00+00:00",
        observed_at=f"2026-10-01T{hours:02d}:00:00+00:00",
        views=views,
        creator_baseline_views=baseline,
        evidence_ref=evidence,
    )


def test_outlier_rewards_relative_and_velocity_performance():
    candidate = obs("candidate", 10000)
    peers = [obs("p1", 1000), obs("p2", 1200), obs("p3", 800)]
    signal = detect_outlier(candidate, peers)
    assert signal.relative_performance == 10.0
    assert signal.velocity_ratio > 8.0
    assert 0.0 < signal.outlier_strength < 1.0
    assert signal.formula_version == "outlier.v1"


def test_cross_platform_peers_are_not_mixed():
    candidate = obs("candidate", 5000)
    peers = [obs("ig", 999999, platform="instagram"), obs("yt", 1000)]
    signal = detect_outlier(candidate, peers)
    assert signal.velocity_ratio == 5.0


def test_observation_requires_provenance():
    bad = obs("bad", 100, evidence="")
    with pytest.raises(ValueError):
        bad.validate()


def test_observation_rejects_impossible_time():
    bad = ContentObservation(
        "youtube", "bad", "c",
        "2026-10-02T00:00:00+00:00",
        "2026-10-01T00:00:00+00:00",
        100, 100, "fixture://bad",
    )
    with pytest.raises(ValueError):
        bad.validate()


def test_evidence_hash_is_stable_and_journaled(tmp_path):
    journal = DecisionJournal(tmp_path / "evidence.db")
    value = obs("x", 100)
    assert evidence_hash(value) == evidence_hash(value)
    record_evidence(journal, "content_observation.v1", value)
    event = journal.read_all()[0]
    assert event["event_type"] == "EVIDENCE"
    assert len(event["payload"]["sha256"]) == 64


def test_outlier_rejects_when_no_same_platform_peer_evidence_exists():
    candidate = obs("candidate", 5000)
    with pytest.raises(ValueError, match="peer baseline"):
        detect_outlier(candidate, [obs("ig", 1000, platform="instagram")])


def test_zero_velocity_peer_cohort_cannot_create_exploding_ratio():
    candidate = obs("candidate", 5000)
    peers = [obs("p1", 0), obs("p2", 0), obs("p3", 0)]
    signal = detect_outlier(candidate, peers)
    assert signal.velocity_ratio == 1.0
