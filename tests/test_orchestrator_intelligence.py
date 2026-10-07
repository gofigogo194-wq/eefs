import pytest

from media_omega.intelligence_pipeline import IntelligenceSignal
from media_omega.memory import DecisionJournal
from media_omega.orchestrator import Orchestrator
from media_omega.state_machine import WorkflowState


def signal(content_id, score, evidence=0.5, status="READY", source_refs=("fixture://source",)):
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
        source_evidence_refs=source_refs,
    )


def test_orchestrator_selects_and_admits_canonical_intelligence_signal(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    winner = engine.choose_intelligence([
        signal("slow", 0.4, 0.9),
        signal("fast", 0.8, 0.7),
    ])
    assert winner.content_id == "fast"
    assert engine.states.current_state("youtube:fast") is WorkflowState.EVIDENCE_COLLECTED

    events = journal.read_all()
    assert events[-1]["event_type"] == "INTELLIGENCE_SELECTION"
    assert events[-1]["payload"]["formula_version"] == "intelligence_pipeline.v4"
    assert events[-1]["payload"]["entity_id"] == "youtube:fast"
    assert events[-1]["payload"]["evidence_ref"].startswith("journal://evidence/")
    assert [x["content_id"] for x in events[-1]["payload"]["ranking"]] == ["fast", "slow"]
    assert [x["event_type"] for x in events].count("STATE_TRANSITION") == 2
    assert [x["event_type"] for x in events].count("EVIDENCE") == 1


def test_repeat_selection_does_not_regress_or_duplicate_state(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    engine.choose_intelligence([signal("fast", 0.8)])
    engine.choose_intelligence([signal("fast", 0.9)])
    assert engine.states.current_state("youtube:fast") is WorkflowState.EVIDENCE_COLLECTED
    assert [x["event_type"] for x in journal.read_all()].count("STATE_TRANSITION") == 2


def test_orchestrator_rejects_non_ready_intelligence_before_journaling(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    with pytest.raises(ValueError, match="READY"):
        engine.choose_intelligence([
            signal("blocked", 10.0, status="INSUFFICIENT_CREATOR_HISTORY")
        ])
    assert journal.read_all() == []


def test_orchestrator_rejects_signal_without_source_provenance(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    with pytest.raises(ValueError, match="source provenance"):
        engine.choose_intelligence([signal("x", 1.0, source_refs=())])
    assert journal.read_all() == []
