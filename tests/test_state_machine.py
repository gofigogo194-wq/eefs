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


def test_full_state_path_is_explicit_and_auditable(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    entity = "youtube:video-1"

    engine.register(entity)
    discovery = receipt(journal, "intelligence_signal.v4", {"content_id": "video-1"})
    engine.transition(
        entity,
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(discovery,)),
    )
    engine.transition(
        entity,
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="plan-1"),
    )
    engine.transition(
        entity,
        WorkflowState.ASSETS_READY,
        TransitionEvidence(asset_refs=("artifact://video-1",)),
    )
    verification = receipt(journal, "verification.v1", {"decision": "ACCEPT"})
    engine.transition(
        entity,
        WorkflowState.VERIFIED,
        TransitionEvidence(
            verification_ref=verification,
            policy_decision="ACCEPT",
        ),
    )
    engine.transition(
        entity,
        WorkflowState.SCHEDULED,
        TransitionEvidence(schedule_id="schedule-1"),
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
    learning = receipt(journal, "learning.v1", {"candidate": "learning-1"})
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
        engine.transition(
            "x",
            WorkflowState.PLANNED,
            TransitionEvidence(plan_id="plan-1"),
        )


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


def test_verified_requires_evidence_and_policy_accept(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    evidence = receipt(journal, "intel.v1", {"x": 1})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(evidence,)),
    )
    engine.transition("x", WorkflowState.PLANNED, TransitionEvidence(plan_id="p"))
    engine.transition(
        "x",
        WorkflowState.ASSETS_READY,
        TransitionEvidence(asset_refs=("artifact://a",)),
    )
    verification = receipt(journal, "verification.v1", {"decision": "BLOCK"})
    with pytest.raises(ValueError, match="policy ACCEPT"):
        engine.transition(
            "x",
            WorkflowState.VERIFIED,
            TransitionEvidence(
                verification_ref=verification,
                policy_decision="BLOCK",
            ),
        )


def test_published_cannot_be_claimed_from_dry_run_receipt(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    evidence = receipt(journal, "intel.v1", {"x": 1})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(evidence,)),
    )
    engine.transition("x", WorkflowState.PLANNED, TransitionEvidence(plan_id="p"))
    engine.transition(
        "x",
        WorkflowState.ASSETS_READY,
        TransitionEvidence(asset_refs=("artifact://a",)),
    )
    verified = receipt(journal, "verification.v1", {"decision": "ACCEPT"})
    engine.transition(
        "x",
        WorkflowState.VERIFIED,
        TransitionEvidence(verification_ref=verified, policy_decision="ACCEPT"),
    )
    engine.transition("x", WorkflowState.SCHEDULED, TransitionEvidence(schedule_id="s"))
    dry_run = receipt(journal, "publication_receipt.v1", {"published": False})
    with pytest.raises(ValueError, match="confirmed publication"):
        engine.transition(
            "x",
            WorkflowState.PUBLISHED,
            TransitionEvidence(
                publication_receipt_ref=dry_run,
                published=False,
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
