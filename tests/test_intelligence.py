from media_omega.intelligence import build_candidate
from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation


def point(content_id, hour, views, baseline=1000, platform="youtube"):
    return ContentObservation(
        platform=platform,
        content_id=content_id,
        creator_id="creator",
        published_at="2026-10-01T00:00:00+00:00",
        observed_at=f"2026-10-01T{hour:02d}:00:00+00:00",
        views=views,
        creator_baseline_views=baseline,
        evidence_ref=f"fixture://{platform}/{content_id}/{hour}",
    )


def test_pipeline_produces_candidate_with_auditable_evidence(tmp_path):
    journal = DecisionJournal(tmp_path / "intel.db")
    history = [point("hot", 1, 100), point("hot", 2, 300), point("hot", 3, 900)]
    peers = [point("peer1", 3, 100), point("peer2", 3, 150), point("peer3", 3, 120)]
    candidate = build_candidate(history, peers, journal)

    assert candidate.content_id == "hot"
    assert candidate.outlier_strength > 0
    assert candidate.acceleration_ratio > 1
    assert candidate.evidence_count == 6
    assert 0 < candidate.confidence < 1

    events = journal.read_all()
    assert [x["event_type"] for x in events].count("EVIDENCE") == 6
    assert events[-1]["event_type"] == "OPPORTUNITY_CANDIDATE"


def test_confidence_is_evidence_sufficiency_not_forced_to_one(tmp_path):
    journal = DecisionJournal(tmp_path / "intel.db")
    history = [point("hot", 1, 100), point("hot", 2, 200), point("hot", 3, 300)]
    peers = [point("peer", 3, 100)]
    candidate = build_candidate(history, peers, journal)
    assert candidate.confidence < 0.5
