from dataclasses import asdict

import pytest

from media_omega.intelligence_pipeline import IntelligenceSignal
from media_omega.memory import DecisionJournal
from media_omega.models import CreativePlan, Decision
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


def report_signals(journal, signals):
    journal.append("INTELLIGENCE_REPORT", {
        "ready": [asdict(value) for value in signals],
        "insufficient_snapshot_history": [],
        "insufficient_creator_history": [],
        "unreliable_creator_baseline": [],
        "unreliable_history": [],
        "required_snapshots": 3,
        "creator_baseline_cache_entries": 0,
    })


def test_orchestrator_selects_and_admits_canonical_intelligence_signal(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    candidates = [
        signal("slow", 0.4, 0.9),
        signal("fast", 0.8, 0.7),
    ]
    report_signals(journal, candidates)
    winner = engine.choose_intelligence(candidates)
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
    first = signal("fast", 0.8)
    second = signal("fast", 0.9)
    report_signals(journal, [first])
    engine.choose_intelligence([first])
    report_signals(journal, [second])
    engine.choose_intelligence([second])
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


def test_orchestrator_rejects_ready_signal_not_emitted_by_intelligence_report(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    fabricated = signal("fabricated", 999.0)
    with pytest.raises(ValueError, match="journaled report"):
        engine.choose_intelligence([fabricated])
    assert journal.read_all() == []


def selected_engine(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    candidate = signal("target", 1.0)
    report_signals(journal, [candidate])
    engine.choose_intelligence([candidate])
    return journal, engine


def plan(plan_id="plan-1", **changes):
    values = dict(
        opportunity_id="youtube:target",
        platform="youtube",
        format="short",
        title="Original concept",
        original=True,
        rights_confirmed=True,
        estimated_cost=1.0,
        id=plan_id,
    )
    values.update(changes)
    return CreativePlan(**values)


def test_selected_opportunity_advances_through_one_plan_policy_gate(tmp_path):
    journal, engine = selected_engine(tmp_path)
    gate = engine.plan_selected(plan())

    assert gate.decision is Decision.ACCEPT
    assert engine.states.current_state("youtube:target") is WorkflowState.PLANNED

    events = journal.read_all()
    assert [event["event_type"] for event in events].count("PLAN_POLICY_DECISION") == 1
    plan_events = [
        event for event in events
        if event["event_type"] == "EVIDENCE"
        and event["payload"]["evidence_type"] == "creative_plan.v1"
    ]
    assert len(plan_events) == 1
    payload = plan_events[0]["payload"]["payload"]
    assert payload["entity_id"] == "youtube:target"
    assert payload["plan_id"] == "plan-1"
    assert payload["policy_decision"] == "ACCEPT"


def test_blocked_plan_attempt_does_not_poison_selected_opportunity(tmp_path):
    journal, engine = selected_engine(tmp_path)
    gate = engine.plan_selected(plan(rights_confirmed=False))

    assert gate.decision is Decision.BLOCK
    assert (
        engine.states.current_state("youtube:target")
        is WorkflowState.EVIDENCE_COLLECTED
    )
    assert not any(
        event["event_type"] == "EVIDENCE"
        and event["payload"].get("evidence_type") == "creative_plan.v1"
        for event in journal.read_all()
    )

    corrected = engine.plan_selected(plan("plan-2", rights_confirmed=True))
    assert corrected.decision is Decision.ACCEPT
    assert engine.states.current_state("youtube:target") is WorkflowState.PLANNED


def test_same_plan_replay_is_idempotent(tmp_path):
    journal, engine = selected_engine(tmp_path)
    candidate = plan()
    engine.plan_selected(candidate)
    event_count = len(journal.read_all())

    gate = engine.plan_selected(candidate)
    assert gate.decision is Decision.ACCEPT
    assert len(journal.read_all()) == event_count
    assert engine.states.current_state("youtube:target") is WorkflowState.PLANNED


def test_different_plan_cannot_silently_replace_planned_opportunity(tmp_path):
    _, engine = selected_engine(tmp_path)
    engine.plan_selected(plan("plan-1"))
    with pytest.raises(ValueError, match="different plan"):
        engine.plan_selected(plan("plan-2"))


def test_plan_requires_previously_selected_opportunity(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    with pytest.raises(ValueError, match="selected before planning"):
        engine.plan_selected(plan())
    assert journal.read_all() == []


def test_same_plan_id_with_changed_payload_is_not_treated_as_idempotent(tmp_path):
    _, engine = selected_engine(tmp_path)
    engine.plan_selected(plan("plan-1", title="Original concept"))
    with pytest.raises(ValueError, match="replay differs"):
        engine.plan_selected(plan("plan-1", title="Changed concept"))


class FakeCreator:
    name = "fake-creator"

    def __init__(self, assets=("artifact://video",)):
        self.assets = assets
        self.calls = []

    def create(self, plan, idempotency_key):
        self.calls.append((plan.id, idempotency_key))
        return self.assets


def planned_engine(tmp_path):
    journal, engine = selected_engine(tmp_path)
    candidate = plan()
    engine.plan_selected(candidate)
    return journal, engine, candidate


def test_planned_opportunity_creates_one_manifest_and_reaches_assets_ready(tmp_path):
    journal, engine, candidate = planned_engine(tmp_path)
    creator = FakeCreator(("artifact://video", "artifact://thumbnail"))

    manifest = engine.create_assets(candidate, creator)

    assert manifest.plan_id == candidate.id
    assert manifest.entity_id == "youtube:target"
    assert manifest.assets == ("artifact://video", "artifact://thumbnail")
    assert creator.calls == [(candidate.id, candidate.id)]
    assert engine.states.current_state("youtube:target") is WorkflowState.ASSETS_READY

    events = journal.read_all()
    manifests = [
        event for event in events
        if event["event_type"] == "EVIDENCE"
        and event["payload"]["evidence_type"] == "asset_manifest.v1"
    ]
    assert len(manifests) == 1
    assert manifests[0]["payload"]["payload"]["plan_id"] == candidate.id


def test_asset_creation_replay_does_not_call_provider_twice(tmp_path):
    journal, engine, candidate = planned_engine(tmp_path)
    creator = FakeCreator()

    first = engine.create_assets(candidate, creator)
    event_count = len(journal.read_all())
    second = engine.create_assets(candidate, creator)

    assert second == first
    assert creator.calls == [(candidate.id, candidate.id)]
    assert len(journal.read_all()) == event_count


@pytest.mark.parametrize("assets", [(), ("",), ("artifact://x", "artifact://x")])
def test_invalid_creator_output_does_not_advance_state(tmp_path, assets):
    _, engine, candidate = planned_engine(tmp_path)
    creator = FakeCreator(assets)

    with pytest.raises(ValueError):
        engine.create_assets(candidate, creator)

    assert engine.states.current_state("youtube:target") is WorkflowState.PLANNED


def test_creator_cannot_use_plan_that_differs_from_admitted_plan(tmp_path):
    _, engine, candidate = planned_engine(tmp_path)
    changed = CreativePlan(
        opportunity_id=candidate.opportunity_id,
        platform=candidate.platform,
        format=candidate.format,
        title="mutated after admission",
        original=candidate.original,
        rights_confirmed=candidate.rights_confirmed,
        estimated_cost=candidate.estimated_cost,
        metadata=candidate.metadata,
        id=candidate.id,
    )

    with pytest.raises(ValueError, match="differs from admitted plan"):
        engine.create_assets(changed, FakeCreator())
