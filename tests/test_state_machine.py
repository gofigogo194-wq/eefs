import pytest

from media_omega.evidence import record_evidence
from media_omega.memory import DecisionJournal
from media_omega.state_machine import (
    StateTransitionEngine,
    TransitionEvidence,
    WorkflowState,
)


def receipt(journal, evidence_type, payload):
    return record_evidence(journal, evidence_type, payload).evidence_ref


def advance_to_assets_ready(journal, engine, entity="x"):
    engine.register(entity)
    intelligence = receipt(journal, "intelligence_signal.v4", {"content_id": entity})
    engine.transition(
        entity,
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intelligence,)),
    )
    plan = receipt(journal, "creative_plan.v1", {"plan_id": "plan-1"})
    engine.transition(
        entity,
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="plan-1", plan_ref=plan),
    )
    assets = receipt(
        journal,
        "asset_manifest.v1",
        {"assets": ["artifact://video-1"]},
    )
    engine.transition(
        entity,
        WorkflowState.ASSETS_READY,
        TransitionEvidence(asset_manifest_refs=(assets,)),
    )


def test_full_state_path_is_explicit_and_auditable(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    entity = "youtube:video-1"

    advance_to_assets_ready(journal, engine, entity)

    verification = receipt(journal, "verification.v1", {"decision": "ACCEPT"})
    engine.transition(
        entity,
        WorkflowState.VERIFIED,
        TransitionEvidence(
            verification_ref=verification,
            policy_decision="ACCEPT",
        ),
    )

    schedule = receipt(
        journal,
        "schedule.v1",
        {"schedule_id": "schedule-1"},
    )
    engine.transition(
        entity,
        WorkflowState.SCHEDULED,
        TransitionEvidence(
            schedule_id="schedule-1",
            schedule_ref=schedule,
        ),
    )

    publication = receipt(
        journal,
        "publication_receipt.v1",
        {"published": True, "remote_id": "remote-1"},
    )
    engine.transition(
        entity,
        WorkflowState.PUBLISHED,
        TransitionEvidence(
            publication_receipt_ref=publication,
            published=True,
        ),
    )

    metrics = receipt(journal, "measurement.v1", {"views": 123})
    engine.transition(
        entity,
        WorkflowState.MEASURED,
        TransitionEvidence(metric_refs=(metrics,)),
    )

    learning = receipt(
        journal,
        "learning.v1",
        {"version": "learning.v1", "candidate": "learning-1"},
    )
    engine.transition(
        entity,
        WorkflowState.LEARNED,
        TransitionEvidence(
            learning_version="learning.v1",
            learning_evidence_ref=learning,
        ),
    )

    assert engine.current_state(entity) is WorkflowState.LEARNED
    assert [x.to_state for x in engine.history(entity)] == [
        WorkflowState.IDEA,
        WorkflowState.EVIDENCE_COLLECTED,
        WorkflowState.PLANNED,
        WorkflowState.ASSETS_READY,
        WorkflowState.VERIFIED,
        WorkflowState.SCHEDULED,
        WorkflowState.PUBLISHED,
        WorkflowState.MEASURED,
        WorkflowState.LEARNED,
    ]
    assert journal.verify_chain() is True


def test_state_machine_rejects_skipped_stage(tmp_path):
    engine = StateTransitionEngine(DecisionJournal(tmp_path / "journal.db"))
    engine.register("x")
    with pytest.raises(ValueError, match="invalid state transition"):
        engine.transition("x", WorkflowState.PLANNED)


def test_evidence_collected_requires_journal_verified_evidence(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    with pytest.raises(ValueError, match="journal-verified"):
        engine.transition(
            "x",
            WorkflowState.EVIDENCE_COLLECTED,
            TransitionEvidence(evidence_refs=("api://youtube/raw",)),
        )


def test_planned_requires_typed_plan_evidence_matching_id(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    intel = receipt(journal, "intelligence_signal.v4", {"x": 1})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    wrong_type = receipt(journal, "measurement.v1", {"plan_id": "plan-1"})
    with pytest.raises(ValueError, match="wrong type"):
        engine.transition(
            "x",
            WorkflowState.PLANNED,
            TransitionEvidence(plan_id="plan-1", plan_ref=wrong_type),
        )
    wrong_id = receipt(journal, "creative_plan.v1", {"plan_id": "other"})
    with pytest.raises(ValueError, match="does not match"):
        engine.transition(
            "x",
            WorkflowState.PLANNED,
            TransitionEvidence(plan_id="plan-1", plan_ref=wrong_id),
        )


def test_assets_ready_requires_manifest_with_assets(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    intel = receipt(journal, "intelligence_signal.v4", {"x": 1})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    plan = receipt(journal, "creative_plan.v1", {"plan_id": "p"})
    engine.transition(
        "x",
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="p", plan_ref=plan),
    )
    empty_manifest = receipt(journal, "asset_manifest.v1", {"assets": []})
    with pytest.raises(ValueError, match="contain assets"):
        engine.transition(
            "x",
            WorkflowState.ASSETS_READY,
            TransitionEvidence(asset_manifest_refs=(empty_manifest,)),
        )


def test_verified_requires_evidence_payload_accept_not_only_caller_flag(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    advance_to_assets_ready(journal, engine)

    blocked = receipt(journal, "verification.v1", {"decision": "BLOCK"})
    with pytest.raises(ValueError, match="record ACCEPT"):
        engine.transition(
            "x",
            WorkflowState.VERIFIED,
            TransitionEvidence(
                verification_ref=blocked,
                policy_decision="ACCEPT",
            ),
        )


def test_schedule_evidence_must_match_schedule_id(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    advance_to_assets_ready(journal, engine)
    verification = receipt(journal, "verification.v1", {"decision": "ACCEPT"})
    engine.transition(
        "x",
        WorkflowState.VERIFIED,
        TransitionEvidence(
            verification_ref=verification,
            policy_decision="ACCEPT",
        ),
    )
    schedule = receipt(journal, "schedule.v1", {"schedule_id": "other"})
    with pytest.raises(ValueError, match="does not match"):
        engine.transition(
            "x",
            WorkflowState.SCHEDULED,
            TransitionEvidence(schedule_id="s", schedule_ref=schedule),
        )


def test_published_cannot_be_claimed_from_dry_run_payload_even_if_flag_lies(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    advance_to_assets_ready(journal, engine)

    verified = receipt(journal, "verification.v1", {"decision": "ACCEPT"})
    engine.transition(
        "x",
        WorkflowState.VERIFIED,
        TransitionEvidence(
            verification_ref=verified,
            policy_decision="ACCEPT",
        ),
    )
    schedule = receipt(journal, "schedule.v1", {"schedule_id": "s"})
    engine.transition(
        "x",
        WorkflowState.SCHEDULED,
        TransitionEvidence(schedule_id="s", schedule_ref=schedule),
    )

    dry_run = receipt(
        journal,
        "publication_receipt.v1",
        {"published": False, "dry_run": True},
    )
    with pytest.raises(ValueError, match="does not confirm publication"):
        engine.transition(
            "x",
            WorkflowState.PUBLISHED,
            TransitionEvidence(
                publication_receipt_ref=dry_run,
                published=True,
            ),
        )


def test_rejected_and_blocked_are_terminal_and_require_reason(tmp_path):
    engine = StateTransitionEngine(DecisionJournal(tmp_path / "journal.db"))
    engine.register("x")
    with pytest.raises(ValueError, match="reason"):
        engine.transition("x", WorkflowState.BLOCKED)
    engine.transition("x", WorkflowState.BLOCKED, reason="policy failure")
    assert engine.current_state("x") is WorkflowState.BLOCKED
    with pytest.raises(ValueError, match="invalid state transition"):
        engine.transition("x", WorkflowState.EVIDENCE_COLLECTED)


def test_duplicate_registration_is_rejected(tmp_path):
    engine = StateTransitionEngine(DecisionJournal(tmp_path / "journal.db"))
    engine.register("x")
    with pytest.raises(ValueError, match="already registered"):
        engine.register("x")


def test_history_revalidates_illegal_edge_even_when_journal_hash_is_valid(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    forged = {
        "entity_id": "x",
        "from_state": "IDEA",
        "to_state": "PUBLISHED",
        "reason": "",
        "evidence": {},
        "contract_version": "state_transition.v1",
    }
    with journal._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = journal._rows(db)
        journal._append_verified(db, rows, "STATE_TRANSITION", forged)
    assert journal.verify_chain() is True
    with pytest.raises(RuntimeError, match="illegal edge"):
        engine.current_state("x")


def test_history_rejects_non_boolean_published_field(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    forged = {
        "entity_id": "x",
        "from_state": "IDEA",
        "to_state": "EVIDENCE_COLLECTED",
        "reason": "",
        "evidence": {
            "evidence_refs": [],
            "published": "false",
        },
        "contract_version": "state_transition.v1",
    }
    with journal._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = journal._rows(db)
        journal._append_verified(db, rows, "STATE_TRANSITION", forged)
    with pytest.raises(RuntimeError, match="published must be a boolean"):
        engine.current_state("x")
