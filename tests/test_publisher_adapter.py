from datetime import datetime, timedelta, timezone
from dataclasses import asdict

import pytest

from media_omega.intelligence_pipeline import IntelligenceSignal
from media_omega.memory import DecisionJournal
from media_omega.models import CreatedAsset, CreativePlan, Decision, GateResult
from media_omega.orchestrator import Orchestrator
from media_omega.publisher_adapter import YouTubeDryRunAdapter
from media_omega.state_machine import WorkflowState


def test_adapter_is_strict_and_has_no_upload():
    adapter = YouTubeDryRunAdapter()
    package = {
        "version": "schedule.v2", "platform": "youtube", "visibility": "private",
        "dry_run_only": True, "schedule_id": "schedule-123", "entity_id": "youtube:one",
    }
    assert not hasattr(adapter, "upload")
    with pytest.raises(ValueError, match="preflight"):
        adapter.prepare(package, GateResult(Decision.BLOCK, ("INVALID",)))
    for change in [
        {"visibility": "public"}, {"dry_run_only": False},
        {"platform": "tiktok"}, {"version": "schedule.v1"},
    ]:
        with pytest.raises(ValueError, match="canonical"):
            adapter.prepare({**package, **change}, GateResult(Decision.ACCEPT, ("PASS",)))
    response = adapter.prepare(package, GateResult(Decision.ACCEPT, ("PASS",)))
    assert response.published is False
    assert response.remote_id is None
    assert response.mode == "DRY_RUN"


def test_orchestrator_offline_publisher_requires_fresh_preflight(tmp_path, monkeypatch):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    signal = IntelligenceSignal(
        content_id="one", creator_id="maker", relative_creator_performance=2.,
        acceleration_ratio=1.5, latest_velocity=10., baseline_confidence=0.5,
        evidence_sufficiency=0.8, score=1., status="READY", platform="youtube",
        source_evidence_refs=("test://source",),
    )
    journal.append("INTELLIGENCE_REPORT", {
        "ready": [asdict(signal)], "insufficient_snapshot_history": [],
        "insufficient_creator_history": [], "unreliable_creator_baseline": [],
        "unreliable_history": [], "required_snapshots": 3,
        "creator_baseline_cache_entries": 0,
    })
    engine.choose_intelligence([signal])
    plan = CreativePlan(
        opportunity_id="youtube:one", platform="youtube", format="long-form",
        title="Original test", original=True, rights_confirmed=True,
        estimated_cost=1., id="publisher-plan",
    )
    assert engine.plan_selected(plan).decision is Decision.ACCEPT
    path = tmp_path / "video.mp4"
    path.write_bytes(b"test-only-fixture")
    class Creator:
        name = "fixture"
        def create(self, plan, idempotency_key):
            return (CreatedAsset("video", str(path), "video/mp4", "test://fixture"),)
    engine.create_assets(plan, Creator())
    assert engine.verify_assets(plan).decision is Decision.ACCEPT

    with pytest.raises(ValueError, match="SCHEDULED"):
        engine.publisher_dry_run(plan)
    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    engine.schedule_dry_run(plan, when)

    # A previous successful probe is not a pass to bypass a current failure.
    monkeypatch.setattr(
        engine, "inspect_verified_video",
        lambda plan: GateResult(Decision.BLOCK, ("VIDEO_DECODE_FAILED",)),
    )
    with pytest.raises(ValueError, match="preflight"):
        engine.publisher_dry_run(plan)
    assert not any(e["event_type"] == "PUBLISHER_DRY_RUN" for e in journal.read_all())

    monkeypatch.setattr(
        engine, "inspect_verified_video",
        lambda plan: GateResult(Decision.ACCEPT, ("VIDEO_DECODE_PASS",)),
    )
    result = engine.publisher_dry_run(plan)
    assert result["published"] is False
    assert result["remote_id"] is None
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.SCHEDULED
    assert not any(
        e["event_type"] == "STATE_TRANSITION" and e["payload"]["to_state"] == "PUBLISHED"
        for e in journal.read_all()
    )
