import pytest

from media_omega.evidence import record_evidence
from media_omega.memory import DecisionJournal
from media_omega.state_machine import (
    StateTransitionEngine,
    TransitionEvidence,
    WorkflowState,
)


def receipt(journal, evidence_type, payload, entity="x"):
    bound = dict(payload)
    bound.setdefault("entity_id", entity)
    return record_evidence(journal, evidence_type, bound).evidence_ref


def asset_record(
    asset_id="video",
    path="/fixture/video.mp4",
    media_type="video/mp4",
):
    return {
        "asset_id": asset_id,
        "path": path,
        "media_type": media_type,
        "sha256": "a" * 64,
        "size_bytes": 1,
        "provenance": f"fixture://{asset_id}",
    }


def manifest_payload(plan_id, assets=None, provider="fixture"):
    if assets is None:
        assets = [asset_record()]
    return {
        "plan_id": plan_id,
        "assets": assets,
        "provider": provider,
        "version": "asset_manifest.v2",
    }


def advance_to_assets_ready(journal, engine, entity="x"):
    engine.register(entity)
    intelligence = receipt(
        journal,
        "intelligence_pipeline.v4",
        {"content_id": entity},
        entity,
    )
    engine.transition(
        entity,
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intelligence,)),
    )
    plan = receipt(
        journal,
        "creative_plan.v1",
        {"plan_id": "plan-1", "policy_decision": "ACCEPT"},
        entity,
    )
    engine.transition(
        entity,
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="plan-1", plan_ref=plan),
    )
    assets = receipt(
        journal,
        "asset_manifest.v2",
        manifest_payload("plan-1"),
        entity,
    )
    engine.transition(
        entity,
        WorkflowState.ASSETS_READY,
        TransitionEvidence(
            plan_id="plan-1",
            asset_manifest_refs=(assets,),
        ),
    )
    return assets


def test_full_state_path_is_explicit_and_auditable(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    entity = "youtube:video-1"

    asset_ref = advance_to_assets_ready(journal, engine, entity)

    verification = receipt(
        journal,
        "verification.v1",
        {
            "decision": "ACCEPT",
            "plan_id": "plan-1",
            "asset_manifest_ref": asset_ref,
        },
        entity,
    )
    engine.transition(
        entity,
        WorkflowState.VERIFIED,
        TransitionEvidence(
            plan_id="plan-1",
            asset_manifest_refs=(asset_ref,),
            verification_ref=verification,
            policy_decision="ACCEPT",
        ),
    )

    schedule = receipt(
        journal,
        "schedule.v1",
        {"schedule_id": "schedule-1"},
        entity,
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
        entity,
    )
    engine.transition(
        entity,
        WorkflowState.PUBLISHED,
        TransitionEvidence(
            publication_receipt_ref=publication,
            published=True,
        ),
    )

    metrics = receipt(
        journal,
        "measurement.v1",
        {"views": 123},
        entity,
    )
    engine.transition(
        entity,
        WorkflowState.MEASURED,
        TransitionEvidence(metric_refs=(metrics,)),
    )

    learning = receipt(
        journal,
        "learning.v1",
        {"version": "learning.v1", "candidate": "learning-1"},
        entity,
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
    intel = receipt(journal, "intelligence_pipeline.v4", {"x": 1})
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
    wrong_id = receipt(
        journal,
        "creative_plan.v1",
        {"plan_id": "other", "policy_decision": "ACCEPT"},
    )
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
    intel = receipt(journal, "intelligence_pipeline.v4", {"x": 1})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    plan = receipt(
        journal,
        "creative_plan.v1",
        {"plan_id": "p", "policy_decision": "ACCEPT"},
    )
    engine.transition(
        "x",
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="p", plan_ref=plan),
    )
    empty_manifest = receipt(
        journal,
        "asset_manifest.v2",
        manifest_payload("p", assets=[]),
    )
    with pytest.raises(ValueError, match="contain assets"):
        engine.transition(
            "x",
            WorkflowState.ASSETS_READY,
            TransitionEvidence(
                plan_id="p",
                asset_manifest_refs=(empty_manifest,),
            ),
        )


def test_verified_requires_evidence_payload_accept_not_only_caller_flag(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    asset_ref = advance_to_assets_ready(journal, engine)

    blocked = receipt(
        journal,
        "verification.v1",
        {
            "decision": "BLOCK",
            "plan_id": "plan-1",
            "asset_manifest_ref": asset_ref,
        },
    )
    with pytest.raises(ValueError, match="record ACCEPT"):
        engine.transition(
            "x",
            WorkflowState.VERIFIED,
            TransitionEvidence(
                plan_id="plan-1",
                asset_manifest_refs=(asset_ref,),
                verification_ref=blocked,
                policy_decision="ACCEPT",
            ),
        )


def test_schedule_evidence_must_match_schedule_id(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    asset_ref = advance_to_assets_ready(journal, engine)
    verification = receipt(
        journal,
        "verification.v1",
        {
            "decision": "ACCEPT",
            "plan_id": "plan-1",
            "asset_manifest_ref": asset_ref,
        },
    )
    engine.transition(
        "x",
        WorkflowState.VERIFIED,
        TransitionEvidence(
            plan_id="plan-1",
            asset_manifest_refs=(asset_ref,),
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
    asset_ref = advance_to_assets_ready(journal, engine)

    verified = receipt(
        journal,
        "verification.v1",
        {
            "decision": "ACCEPT",
            "plan_id": "plan-1",
            "asset_manifest_ref": asset_ref,
        },
    )
    engine.transition(
        "x",
        WorkflowState.VERIFIED,
        TransitionEvidence(
            plan_id="plan-1",
            asset_manifest_refs=(asset_ref,),
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


def test_transition_rejects_evidence_owned_by_another_entity(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    foreign = receipt(
        journal,
        "intelligence_pipeline.v4",
        {"content_id": "foreign"},
        entity="y",
    )
    with pytest.raises(ValueError, match="another entity"):
        engine.transition(
            "x",
            WorkflowState.EVIDENCE_COLLECTED,
            TransitionEvidence(evidence_refs=(foreign,)),
        )


def test_future_evidence_cannot_retroactively_validate_past_transition(tmp_path):
    payload = {"entity_id": "x", "content_id": "x"}
    template = DecisionJournal(tmp_path / "template.db")
    future_ref = record_evidence(
        template,
        "intelligence_pipeline.v4",
        payload,
    ).evidence_ref

    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    journal.append_state_transition(
        {
            "entity_id": "x",
            "from_state": "IDEA",
            "to_state": "EVIDENCE_COLLECTED",
            "reason": "",
            "evidence": {
                "evidence_refs": [future_ref],
                "plan_id": "",
                "plan_ref": "",
                "asset_manifest_refs": [],
                "verification_ref": "",
                "policy_decision": "",
                "schedule_id": "",
                "schedule_ref": "",
                "publication_receipt_ref": "",
                "published": False,
                "metric_refs": [],
                "learning_version": "",
                "learning_evidence_ref": "",
            },
            "contract_version": "state_transition.v1",
        },
        expected_from_state="IDEA",
    )
    record_evidence(journal, "intelligence_pipeline.v4", payload)

    assert journal.verify_chain() is True
    with pytest.raises(RuntimeError, match="evidence contract"):
        engine.current_state("x")


def test_assets_ready_rejects_manifest_for_different_admitted_plan(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    intel = receipt(journal, "intelligence_pipeline.v4", {"x": 1})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    plan_ref = receipt(
        journal,
        "creative_plan.v1",
        {"plan_id": "p1", "policy_decision": "ACCEPT"},
    )
    engine.transition(
        "x",
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="p1", plan_ref=plan_ref),
    )
    manifest = receipt(
        journal,
        "asset_manifest.v2",
        manifest_payload("p2"),
    )
    with pytest.raises(ValueError, match="admitted plan"):
        engine.transition(
            "x",
            WorkflowState.ASSETS_READY,
            TransitionEvidence(
                plan_id="p2",
                asset_manifest_refs=(manifest,),
            ),
        )


def test_assets_ready_rejects_invalid_manifest_semantics(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    intel = receipt(journal, "intelligence_pipeline.v4", {"x": 1})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    plan_ref = receipt(
        journal,
        "creative_plan.v1",
        {"plan_id": "p", "policy_decision": "ACCEPT"},
    )
    engine.transition(
        "x",
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="p", plan_ref=plan_ref),
    )
    bad_manifest = receipt(
        journal,
        "asset_manifest.v2",
        manifest_payload("p", provider=""),
    )
    with pytest.raises(ValueError, match="provider"):
        engine.transition(
            "x",
            WorkflowState.ASSETS_READY,
            TransitionEvidence(
                plan_id="p",
                asset_manifest_refs=(bad_manifest,),
            ),
        )


def test_evidence_collected_rejects_wrong_typed_evidence(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    wrong = receipt(journal, "measurement.v1", {"views": 1})
    with pytest.raises(ValueError, match="wrong type"):
        engine.transition(
            "x",
            WorkflowState.EVIDENCE_COLLECTED,
            TransitionEvidence(evidence_refs=(wrong,)),
        )


def test_planned_requires_policy_accept_in_plan_evidence(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    intel = receipt(journal, "intelligence_pipeline.v4", {"content_id": "x"})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    plan_ref = receipt(journal, "creative_plan.v1", {"plan_id": "p"})
    with pytest.raises(ValueError, match="policy ACCEPT"):
        engine.transition(
            "x",
            WorkflowState.PLANNED,
            TransitionEvidence(plan_id="p", plan_ref=plan_ref),
        )


def test_assets_ready_requires_one_canonical_manifest(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    intel = receipt(journal, "intelligence_pipeline.v4", {"content_id": "x"})
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    plan_ref = receipt(
        journal,
        "creative_plan.v1",
        {"plan_id": "p", "policy_decision": "ACCEPT"},
    )
    engine.transition(
        "x",
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="p", plan_ref=plan_ref),
    )
    first = receipt(
        journal,
        "asset_manifest.v2",
        manifest_payload(
            "p",
            assets=[asset_record("a", "/fixture/a.mp4")],
        ),
    )
    second = receipt(
        journal,
        "asset_manifest.v2",
        manifest_payload(
            "p",
            assets=[asset_record("b", "/fixture/b.mp4")],
        ),
    )
    with pytest.raises(ValueError, match="exactly one"):
        engine.transition(
            "x",
            WorkflowState.ASSETS_READY,
            TransitionEvidence(
                plan_id="p",
                asset_manifest_refs=(first, second),
            ),
        )


def test_verified_must_bind_to_exact_assets_ready_manifest(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    admitted_ref = advance_to_assets_ready(journal, engine)
    alternate_ref = receipt(
        journal,
        "asset_manifest.v2",
        manifest_payload(
            "plan-1",
            assets=[
                asset_record(
                    "alternate",
                    "/fixture/alternate.mp4",
                )
            ],
        ),
    )
    verification = receipt(
        journal,
        "verification.v1",
        {
            "decision": "ACCEPT",
            "plan_id": "plan-1",
            "asset_manifest_ref": alternate_ref,
        },
    )
    with pytest.raises(ValueError, match="does not match ASSETS_READY"):
        engine.transition(
            "x",
            WorkflowState.VERIFIED,
            TransitionEvidence(
                plan_id="plan-1",
                asset_manifest_refs=(alternate_ref,),
                verification_ref=verification,
                policy_decision="ACCEPT",
            ),
        )
    assert admitted_ref != alternate_ref



def test_new_assets_ready_transition_rejects_legacy_manifest_v1(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = StateTransitionEngine(journal)
    engine.register("x")
    intel = receipt(
        journal,
        "intelligence_pipeline.v4",
        {"content_id": "x"},
    )
    engine.transition(
        "x",
        WorkflowState.EVIDENCE_COLLECTED,
        TransitionEvidence(evidence_refs=(intel,)),
    )
    plan_ref = receipt(
        journal,
        "creative_plan.v1",
        {"plan_id": "p", "policy_decision": "ACCEPT"},
    )
    engine.transition(
        "x",
        WorkflowState.PLANNED,
        TransitionEvidence(plan_id="p", plan_ref=plan_ref),
    )
    legacy = receipt(
        journal,
        "asset_manifest.v1",
        {
            "plan_id": "p",
            "assets": ["artifact://legacy"],
            "provider": "legacy",
        },
    )
    with pytest.raises(ValueError, match="read-only"):
        engine.transition(
            "x",
            WorkflowState.ASSETS_READY,
            TransitionEvidence(
                plan_id="p",
                asset_manifest_refs=(legacy,),
            ),
        )
