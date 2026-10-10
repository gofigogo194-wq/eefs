from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from media_omega.intelligence_pipeline import IntelligenceSignal
from media_omega.memory import DecisionJournal
from media_omega.models import CreatedAsset, CreativePlan, Decision
from media_omega.orchestrator import Orchestrator
from media_omega.state_machine import WorkflowState


class Creator:
    name = "test-creator"

    def __init__(self, path):
        self.path = path

    def create(self, plan, idempotency_key):
        assert idempotency_key == plan.id
        return (CreatedAsset("video", str(self.path), "video/mp4", "test://generated"),)


def prepared(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    signal = IntelligenceSignal(
        content_id="one", creator_id="maker", relative_creator_performance=2.0,
        acceleration_ratio=1.5, latest_velocity=10.0, baseline_confidence=0.5,
        evidence_sufficiency=0.8, score=1.0, status="READY", platform="youtube",
        source_evidence_refs=("test://signal",),
    )
    journal.append("INTELLIGENCE_REPORT", {
        "ready": [asdict(signal)],
        "insufficient_snapshot_history": [],
        "insufficient_creator_history": [],
        "unreliable_creator_baseline": [],
        "unreliable_history": [],
        "required_snapshots": 3,
        "creator_baseline_cache_entries": 0,
    })
    engine.choose_intelligence([signal])
    plan = CreativePlan(
        opportunity_id="youtube:one", platform="youtube", format="long-form",
        title="Test video", original=True, rights_confirmed=True,
        estimated_cost=1.0, id="plan-schedule",
    )
    assert engine.plan_selected(plan).decision is Decision.ACCEPT
    path = tmp_path / "video.mp4"
    path.write_bytes(b"test-video-bytes")
    engine.create_assets(plan, Creator(path))
    assert engine.verify_assets(plan).decision is Decision.ACCEPT
    return engine, plan, path


def future():
    return (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()


def test_schedule_dry_run_idempotent_and_never_published(tmp_path):
    engine, plan, _ = prepared(tmp_path)
    time = future()
    receipt = engine.schedule_dry_run(plan, time, description="description")
    count = len(engine.journal.read_all())
    assert receipt["published"] is False
    assert receipt["remote_id"] is None
    assert receipt["mode"] == "DRY_RUN"
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.SCHEDULED
    reopened = Orchestrator(DecisionJournal(tmp_path / "journal.db"))
    assert reopened.schedule_dry_run(plan, time, description="description") == receipt
    assert len(reopened.journal.read_all()) == count
    assert reopened.journal.verify_chain()


def test_schedule_denies_changes_and_invalid_visibility(tmp_path):
    engine, plan, _ = prepared(tmp_path)
    time = future()
    with pytest.raises(ValueError, match="private"):
        engine.schedule_dry_run(plan, time, visibility="public")
    with pytest.raises(ValueError, match="timezone"):
        engine.schedule_dry_run(plan, "2035-01-01T10:00:00")
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.VERIFIED
    engine.schedule_dry_run(plan, time)
    with pytest.raises(ValueError, match="different package"):
        engine.schedule_dry_run(plan, time, description="changed")


def test_schedule_rehash_blocks_modified_and_deleted_files(tmp_path):
    engine, plan, path = prepared(tmp_path)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity"):
        engine.schedule_dry_run(plan, future())
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.VERIFIED
    path.unlink()
    with pytest.raises(ValueError, match="integrity"):
        engine.schedule_dry_run(plan, future())


def test_schedule_never_confirms_publication(tmp_path):
    engine, plan, _ = prepared(tmp_path)
    engine.schedule_dry_run(plan, future())
    assert not any(
        e["event_type"] == "STATE_TRANSITION"
        and e["payload"].get("to_state") == "PUBLISHED"
        for e in engine.journal.read_all()
    )


def test_verified_video_preflight_records_real_media_result(tmp_path, monkeypatch):
    engine, plan, path = prepared(tmp_path)
    from media_omega.models import GateResult
    def inspect(file_path):
        assert file_path == str(path.resolve())
        return GateResult(Decision.ACCEPT, ("VIDEO_PROBE_PASS",)), {
            "version": "video_probe.v1", "video_codec": "h264",
            "audio_present": True, "duration_seconds": 7.0,
        }
    monkeypatch.setattr("media_omega.orchestrator.inspect_video", inspect)
    monkeypatch.setattr(
        "media_omega.orchestrator.decode_video",
        lambda path: GateResult(Decision.ACCEPT, ("VIDEO_DECODE_PASS",)),
    )
    gate = engine.inspect_verified_video(plan)
    assert gate.decision is Decision.ACCEPT
    evidence = [x for x in engine.journal.read_all() if x["event_type"] == "VIDEO_PREFLIGHT"]
    assert len(evidence) == 1
    assert evidence[0]["payload"]["decision"] == "ACCEPT"
    assert evidence[0]["payload"]["media"]["duration_seconds"] == 7.0
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.VERIFIED


def test_verified_video_preflight_refuses_mutated_file(tmp_path, monkeypatch):
    engine, plan, path = prepared(tmp_path)
    path.write_bytes(b"tampered")
    def should_not_probe(file_path):
        pytest.fail("probe must not run when hash has changed")
    monkeypatch.setattr("media_omega.orchestrator.inspect_video", should_not_probe)
    gate = engine.inspect_verified_video(plan)
    assert gate.decision is Decision.BLOCK
    assert "MISMATCH" in repr(gate.reasons)
