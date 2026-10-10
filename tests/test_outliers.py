import pytest

from media_omega.evidence import evidence_hash, evidence_ref_exists, record_evidence
from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation


def obs(content_id, views, baseline=0, hours=10, platform="youtube", evidence="fixture://x"):
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


def test_observation_requires_provenance():
    bad = obs("bad", 100, evidence="")
    with pytest.raises(ValueError):
        bad.validate()


def test_observation_rejects_impossible_time():
    bad = ContentObservation(
        "youtube", "bad", "c",
        "2026-10-02T00:00:00+00:00",
        "2026-10-01T00:00:00+00:00",
        100, 0, "fixture://bad",
    )
    with pytest.raises(ValueError):
        bad.validate()


def test_evidence_hash_is_stable_and_journaled(tmp_path):
    journal = DecisionJournal(tmp_path / "evidence.db")
    value = obs("x", 100)
    assert evidence_hash(value) == evidence_hash(value)
    receipt = record_evidence(journal, "content_observation.v1", value)
    assert receipt.evidence_ref.startswith("journal://evidence/")
    assert evidence_ref_exists(journal, receipt.evidence_ref) is True
    event = journal.read_all()[0]
    assert event["event_type"] == "EVIDENCE"
    assert len(event["payload"]["sha256"]) == 64


def test_evidence_type_is_required(tmp_path):
    journal = DecisionJournal(tmp_path / "evidence.db")
    with pytest.raises(ValueError, match="evidence_type"):
        record_evidence(journal, "   ", {"x": 1})


def test_external_reference_is_not_accepted_as_journal_evidence(tmp_path):
    journal = DecisionJournal(tmp_path / "evidence.db")
    assert evidence_ref_exists(journal, "api://youtube/video") is False


def test_same_payload_under_different_evidence_types_has_distinct_reference(tmp_path):
    journal = DecisionJournal(tmp_path / "evidence.db")
    a = record_evidence(journal, "type.a", {"x": 1})
    b = record_evidence(journal, "type.b", {"x": 1})
    assert a.evidence_ref != b.evidence_ref
    assert evidence_ref_exists(journal, a.evidence_ref)
    assert evidence_ref_exists(journal, b.evidence_ref)


def test_evidence_rejects_non_finite_json_numbers(tmp_path):
    journal = DecisionJournal(tmp_path / "evidence.db")
    with pytest.raises(ValueError):
        record_evidence(journal, "measurement.v1", {"score": float("nan")})
    assert journal.read_all() == []
