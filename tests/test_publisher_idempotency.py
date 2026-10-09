from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from media_omega.memory import DecisionJournal
from media_omega.state_machine import StateTransitionEngine, TransitionEvidence, WorkflowState
from media_omega.evidence import record_evidence


def receipt(schedule="schedule-abc"):
    return {
        "version": "publisher_adapter_dry_run.v1",
        "entity_id": "youtube:one",
        "schedule_id": schedule,
        "published": False,
        "remote_id": None,
        "mode": "DRY_RUN",
    }



def seeded_journal(path):
    journal = DecisionJournal(path)
    engine = StateTransitionEngine(journal)
    engine.register("youtube:one")
    intel = record_evidence(journal, "intelligence_pipeline.v4", {"entity_id": "youtube:one"}).evidence_ref
    engine.transition("youtube:one", WorkflowState.EVIDENCE_COLLECTED, TransitionEvidence(evidence_refs=(intel,)))
    plan = record_evidence(journal, "creative_plan.v1", {"entity_id": "youtube:one", "plan_id": "p", "policy_decision": "ACCEPT"}).evidence_ref
    engine.transition("youtube:one", WorkflowState.PLANNED, TransitionEvidence(plan_id="p", plan_ref=plan))
    asset = record_evidence(journal, "asset_manifest.v2", {
        "version": "asset_manifest.v2", "entity_id": "youtube:one", "plan_id": "p",
        "provider": "fixture", "assets": [{"asset_id": "a", "path": "/fixture/video.mp4",
        "media_type": "video/mp4", "sha256": "a" * 64, "size_bytes": 1, "provenance": "fixture"}],
    }).evidence_ref
    engine.transition("youtube:one", WorkflowState.ASSETS_READY, TransitionEvidence(plan_id="p", asset_manifest_refs=(asset,)))
    checked = record_evidence(journal, "verification.v1", {
        "entity_id": "youtube:one", "plan_id": "p", "asset_manifest_ref": asset,
        "decision": "ACCEPT",
    }).evidence_ref
    engine.transition("youtube:one", WorkflowState.VERIFIED, TransitionEvidence(
        plan_id="p", asset_manifest_refs=(asset,), verification_ref=checked, policy_decision="ACCEPT",
    ))
    schedule = record_evidence(journal, "schedule.v2", {
        "version": "schedule.v2", "entity_id": "youtube:one", "plan_id": "p",
        "manifest_ref": asset, "verification_ref": checked, "platform": "youtube",
        "visibility": "private", "dry_run_only": True, "schedule_id": "schedule-abc",
    }).evidence_ref
    engine.transition("youtube:one", WorkflowState.SCHEDULED, TransitionEvidence(
        plan_id="p", asset_manifest_refs=(asset,), verification_ref=checked,
        schedule_id="schedule-abc", schedule_ref=schedule,
    ))
    return journal

def test_atomic_replay_and_restart_does_not_duplicate(tmp_path):
    path = tmp_path / "journal.db"
    one = seeded_journal(path)
    expected = receipt()
    assert one.append_publisher_dry_run_once(expected) == expected
    second = DecisionJournal(path)
    assert second.append_publisher_dry_run_once(expected) == expected
    assert len([e for e in second.read_all() if e["event_type"] == "PUBLISHER_DRY_RUN"]) == 1
    assert second.verify_chain()


def test_concurrent_writers_one_receipt(tmp_path):
    path = tmp_path / "journal.db"
    seeded_journal(path)
    def invoke(_):
        return DecisionJournal(path).append_publisher_dry_run_once(receipt())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(invoke, range(20)))
    assert all(result == receipt() for result in results)
    journal = DecisionJournal(path)
    assert len([e for e in journal.read_all() if e["event_type"] == "PUBLISHER_DRY_RUN"]) == 1
    assert journal.verify_chain()


def test_conflicting_replay_fails_closed(tmp_path):
    journal = seeded_journal(tmp_path / "journal.db")
    journal.append_publisher_dry_run_once(receipt())
    other = {**receipt(), "extra": "conflict"}
    with pytest.raises(RuntimeError, match="conflicts"):
        journal.append_publisher_dry_run_once(other)
    assert len([e for e in journal.read_all() if e["event_type"] == "PUBLISHER_DRY_RUN"]) == 1


def test_invalid_success_or_remote_claim_blocked(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    for payload in [
        {**receipt(), "published": True},
        {**receipt(), "remote_id": "remote"},
        {**receipt(), "mode": "LIVE"},
        {**receipt(), "schedule_id": ""},
    ]:
        with pytest.raises(ValueError, match="invalid"):
            journal.append_publisher_dry_run_once(payload)
    assert not any(e["event_type"] == "PUBLISHER_DRY_RUN" for e in journal.read_all())


def test_corrupted_journal_blocks_receipt(tmp_path):
    journal = seeded_journal(tmp_path / "journal.db")
    journal.append_publisher_dry_run_once(receipt())
    with sqlite3.connect(journal.path) as conn:
        conn.execute("DROP TRIGGER events_append_only_update")
        conn.execute("UPDATE events SET payload_json='{}' WHERE event_type='PUBLISHER_DRY_RUN'")
    with pytest.raises(RuntimeError, match="hash chain"):
        journal.append_publisher_dry_run_once(receipt())

def test_orphan_receipt_rejected_before_insert(tmp_path):
    journal = DecisionJournal(tmp_path / "empty.db")
    with pytest.raises(ValueError, match="admitted schedule"):
        journal.append_publisher_dry_run_once(receipt())
    assert journal.read_all() == []


def test_crash_during_transaction_rolls_back(tmp_path, monkeypatch):
    journal = seeded_journal(tmp_path / "journal.db")
    from media_omega import memory
    original = memory.DecisionJournal._append_verified

    def interrupted(db, rows, event_type, payload):
        if event_type == "PUBLISHER_DRY_RUN":
            original(db, rows, event_type, payload)
            raise RuntimeError("simulated power loss before commit")
        return original(db, rows, event_type, payload)

    monkeypatch.setattr(memory.DecisionJournal, "_append_verified", staticmethod(interrupted))
    with pytest.raises(RuntimeError, match="simulated power loss"):
        journal.append_publisher_dry_run_once(receipt())
    monkeypatch.setattr(memory.DecisionJournal, "_append_verified", staticmethod(original))
    recovered = DecisionJournal(journal.path)
    assert not any(x["event_type"] == "PUBLISHER_DRY_RUN" for x in recovered.read_all())
    assert recovered.append_publisher_dry_run_once(receipt()) == receipt()
    assert sum(x["event_type"] == "PUBLISHER_DRY_RUN" for x in recovered.read_all()) == 1
    assert recovered.verify_chain()
