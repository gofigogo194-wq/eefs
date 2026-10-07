import pytest

from media_omega.intelligence_pipeline import IntelligenceSignal
from media_omega.memory import DecisionJournal
from media_omega.orchestrator import Orchestrator


def signal(content_id, score, evidence=0.5, status="READY"):
    return IntelligenceSignal(
        content_id=content_id,
        creator_id="creator",
        relative_creator_performance=2.0,
        acceleration_ratio=1.5,
        latest_velocity=10.0,
        baseline_confidence=0.5,
        evidence_sufficiency=evidence,
        score=score,
        status=status,
    )


def test_orchestrator_selects_canonical_intelligence_signal(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    winner = engine.choose_intelligence([
        signal("slow", 0.4, 0.9),
        signal("fast", 0.8, 0.7),
    ])
    assert winner.content_id == "fast"
    event = journal.read_all()[-1]
    assert event["event_type"] == "INTELLIGENCE_SELECTION"
    assert event["payload"]["formula_version"] == "intelligence_pipeline.v3"
    assert [x["content_id"] for x in event["payload"]["ranking"]] == ["fast", "slow"]


def test_orchestrator_rejects_non_ready_intelligence(tmp_path):
    engine = Orchestrator(DecisionJournal(tmp_path / "journal.db"))
    with pytest.raises(ValueError, match="READY"):
        engine.choose_intelligence([signal("blocked", 10.0, status="INSUFFICIENT_CREATOR_HISTORY")])
