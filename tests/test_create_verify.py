from dataclasses import asdict

import pytest

from media_omega.intelligence_pipeline import IntelligenceSignal
from media_omega.memory import DecisionJournal
from media_omega.models import CreatedAsset, CreativePlan, Decision
from media_omega.orchestrator import Orchestrator
from media_omega.state_machine import WorkflowState


def signal(platform="youtube"):
    return IntelligenceSignal(
        content_id="target",
        creator_id="creator",
        relative_creator_performance=2.0,
        acceleration_ratio=1.5,
        latest_velocity=10.0,
        baseline_confidence=0.5,
        evidence_sufficiency=0.8,
        score=1.0,
        status="READY",
        platform=platform,
        source_evidence_refs=("fixture://source",),
    )


def planned_engine(tmp_path, platform="youtube"):
    journal = DecisionJournal(tmp_path / "journal.db")
    engine = Orchestrator(journal)
    candidate = signal(platform)
    journal.append("INTELLIGENCE_REPORT", {
        "ready": [asdict(candidate)],
        "insufficient_snapshot_history": [],
        "insufficient_creator_history": [],
        "unreliable_creator_baseline": [],
        "unreliable_history": [],
        "required_snapshots": 3,
        "creator_baseline_cache_entries": 0,
    })
    engine.choose_intelligence([candidate])
    plan = CreativePlan(
        opportunity_id=f"{platform}:target",
        platform=platform,
        format="long-form",
        title="Original fixture concept",
        original=True,
        rights_confirmed=True,
        estimated_cost=1.0,
        id="plan-1",
    )
    assert engine.plan_selected(plan).decision is Decision.ACCEPT
    return journal, engine, plan


def make_asset(
    root,
    asset_id="video",
    filename="video.mp4",
    data=b"fixture-video",
    media_type="video/mp4",
    provenance="fixture://creator/video",
):
    path = root / filename
    path.write_bytes(data)
    return CreatedAsset(
        asset_id=asset_id,
        path=str(path),
        media_type=media_type,
        provenance=provenance,
    )


class Creator:
    name = "fixture-creator"

    def __init__(self, assets=(), error=None):
        self.assets = assets
        self.error = error
        self.calls = 0

    def create(self, plan, idempotency_key):
        self.calls += 1
        assert idempotency_key == plan.id
        if self.error is not None:
            raise self.error
        return self.assets


def evidence_types(journal):
    return [
        event["payload"].get("evidence_type")
        for event in journal.read_all()
        if event["event_type"] == "EVIDENCE"
    ]


def test_zero_byte_asset_never_reaches_assets_ready(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    creator = Creator((
        make_asset(tmp_path, data=b""),
    ))

    with pytest.raises(ValueError, match="must not be empty"):
        engine.create_assets(plan, creator)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.PLANNED
    assert "asset_manifest.v2" not in evidence_types(journal)


def test_missing_asset_never_reaches_assets_ready(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    creator = Creator((
        CreatedAsset(
            asset_id="video",
            path=str(tmp_path / "missing.mp4"),
            media_type="video/mp4",
            provenance="fixture://missing",
        ),
    ))

    with pytest.raises(ValueError, match="does not exist"):
        engine.create_assets(plan, creator)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.PLANNED
    assert "asset_manifest.v2" not in evidence_types(journal)


def test_duplicate_asset_id_is_rejected_before_manifest_evidence(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    creator = Creator((
        make_asset(tmp_path, "same", "a.mp4", b"a"),
        make_asset(tmp_path, "same", "b.mp4", b"b"),
    ))

    with pytest.raises(ValueError, match="ids must be unique"):
        engine.create_assets(plan, creator)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.PLANNED
    assert "asset_manifest.v2" not in evidence_types(journal)


def test_duplicate_asset_path_is_rejected_before_manifest_evidence(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    asset = make_asset(tmp_path)
    creator = Creator((
        asset,
        CreatedAsset(
            asset_id="other",
            path=asset.path,
            media_type="video/mp4",
            provenance="fixture://creator/other",
        ),
    ))

    with pytest.raises(ValueError, match="paths must be unique"):
        engine.create_assets(plan, creator)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.PLANNED
    assert "asset_manifest.v2" not in evidence_types(journal)


def test_missing_provenance_is_rejected_before_manifest_evidence(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    creator = Creator((
        make_asset(tmp_path, provenance=""),
    ))

    with pytest.raises(ValueError, match="provenance"):
        engine.create_assets(plan, creator)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.PLANNED
    assert "asset_manifest.v2" not in evidence_types(journal)


def test_creator_exception_leaves_retryable_planned_state(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    creator = Creator(error=RuntimeError("provider failed"))

    with pytest.raises(RuntimeError, match="provider failed"):
        engine.create_assets(plan, creator)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.PLANNED
    assert "asset_manifest.v2" not in evidence_types(journal)


def test_mutated_asset_is_blocked_and_never_reaches_verified(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    asset = make_asset(tmp_path)
    manifest = engine.create_assets(plan, Creator((asset,)))
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.ASSETS_READY

    path = tmp_path / "video.mp4"
    path.write_bytes(b"mutated-after-create")

    gate = engine.verify_assets(plan)

    assert gate.decision is Decision.BLOCK
    assert any("MISMATCH" in reason for reason in gate.reasons)
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.ASSETS_READY
    assert manifest.assets[0].sha256
    verification_events = [
        event for event in journal.read_all()
        if event["event_type"] == "EVIDENCE"
        and event["payload"].get("evidence_type") == "verification.v1"
    ]
    assert verification_events[-1]["payload"]["payload"]["decision"] == "BLOCK"


def test_deleted_asset_is_blocked_and_never_reaches_verified(tmp_path):
    _, engine, plan = planned_engine(tmp_path)
    asset = make_asset(tmp_path)
    engine.create_assets(plan, Creator((asset,)))
    (tmp_path / "video.mp4").unlink()

    gate = engine.verify_assets(plan)

    assert gate.decision is Decision.BLOCK
    assert any("UNREADABLE" in reason for reason in gate.reasons)
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.ASSETS_READY


def test_platform_media_constraint_is_checked_on_real_manifest(tmp_path):
    _, engine, plan = planned_engine(tmp_path, platform="youtube")
    image = make_asset(
        tmp_path,
        asset_id="thumbnail",
        filename="thumbnail.png",
        data=b"png-bytes",
        media_type="image/png",
        provenance="fixture://creator/thumbnail",
    )
    engine.create_assets(plan, Creator((image,)))

    gate = engine.verify_assets(plan)

    assert gate.decision is Decision.BLOCK
    assert "PLATFORM_MEDIA_MISMATCH" in gate.reasons
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.ASSETS_READY


def test_successful_verification_reaches_verified_and_is_idempotent(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    engine.create_assets(plan, Creator((make_asset(tmp_path),)))

    first = engine.verify_assets(plan)
    event_count = len(journal.read_all())
    second = engine.verify_assets(plan)

    assert first.decision is Decision.ACCEPT
    assert second == type(second)(
        Decision.ACCEPT,
        ("ASSETS_ALREADY_VERIFIED",),
    )
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.VERIFIED
    assert len(journal.read_all()) == event_count
    assert evidence_types(journal).count("verification.v1") == 1


def test_restart_between_create_and_verify_is_safe(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    engine.create_assets(plan, Creator((make_asset(tmp_path),)))
    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.ASSETS_READY

    reopened = Orchestrator(DecisionJournal(tmp_path / "journal.db"))
    gate = reopened.verify_assets(plan)

    assert gate.decision is Decision.ACCEPT
    assert reopened.states.current_state(plan.opportunity_id) is WorkflowState.VERIFIED
    assert reopened.journal.verify_chain() is True


def test_restart_after_verified_preserves_verified_and_replay_is_safe(tmp_path):
    journal, engine, plan = planned_engine(tmp_path)
    engine.create_assets(plan, Creator((make_asset(tmp_path),)))
    assert engine.verify_assets(plan).decision is Decision.ACCEPT
    event_count = len(journal.read_all())

    reopened = Orchestrator(DecisionJournal(tmp_path / "journal.db"))
    replay = reopened.verify_assets(plan)

    assert replay.decision is Decision.ACCEPT
    assert replay.reasons == ("ASSETS_ALREADY_VERIFIED",)
    assert reopened.states.current_state(plan.opportunity_id) is WorkflowState.VERIFIED
    assert len(reopened.journal.read_all()) == event_count


def test_changed_plan_payload_cannot_verify_admitted_assets(tmp_path):
    _, engine, plan = planned_engine(tmp_path)
    engine.create_assets(plan, Creator((make_asset(tmp_path),)))
    changed = CreativePlan(
        opportunity_id=plan.opportunity_id,
        platform=plan.platform,
        format=plan.format,
        title="mutated plan title",
        original=plan.original,
        rights_confirmed=plan.rights_confirmed,
        estimated_cost=plan.estimated_cost,
        metadata=plan.metadata,
        id=plan.id,
    )

    with pytest.raises(ValueError, match="differs from admitted plan"):
        engine.verify_assets(changed)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.ASSETS_READY


def test_unexpected_verifier_exception_does_not_advance_state(
    tmp_path,
    monkeypatch,
):
    journal, engine, plan = planned_engine(tmp_path)
    engine.create_assets(plan, Creator((make_asset(tmp_path),)))

    def explode(manifest, admitted_plan):
        raise RuntimeError("verification infrastructure failed")

    monkeypatch.setattr(
        "media_omega.orchestrator.verify_asset_manifest",
        explode,
    )

    with pytest.raises(RuntimeError, match="verification infrastructure"):
        engine.verify_assets(plan)

    assert engine.states.current_state(plan.opportunity_id) is WorkflowState.ASSETS_READY
    assert "verification.v1" not in evidence_types(journal)
