from media_omega.discovery import DiscoveryPolicy
from media_omega.evidence import resolve_evidence
from media_omega.intelligence_report import analyze_intelligence
from media_omega.memory import DecisionJournal
from media_omega.models import CreatedAsset, CreativePlan, Decision
from media_omega.orchestrator import Orchestrator
from media_omega.refresh import refresh_tracked
from media_omega.runtime import run_readonly_cycle
from media_omega.scout import ScoutPolicy, ScoutTopic
from media_omega.snapshots import SnapshotStore
from media_omega.state_machine import WorkflowState


class Transport:
    def __init__(self):
        self.stats_round = 0

    def discover_videos(self, query):
        return [{
            "content_id": "target",
            "creator_id": "creator",
            "title": "Ambient opportunity",
            "published_at": "2026-10-07T00:00:00+00:00",
            "evidence_ref": "api://youtube/search/target",
        }]

    def video_statistics(self, ids):
        values = [1000, 2000, 5000]
        value = values[min(self.stats_round, len(values) - 1)]
        self.stats_round += 1
        return {content_id: value for content_id in ids}

    def channel_recent_video_ids(self, creator_id):
        return ["old-1", "old-2", "old-3"]

    def video_details(self, ids):
        return {
            content_id: {
                "views": 1000,
                "published_at": "2026-10-07T00:00:00+00:00",
                "observed_at": "2026-10-07T03:00:00+00:00",
            }
            for content_id in ids
        }


class Creator:
    name = "fixture-creator"

    def __init__(self, root):
        self.root = root

    def create(self, plan, idempotency_key):
        assert idempotency_key == plan.id
        video = self.root / "video.mp4"
        thumbnail = self.root / "thumbnail.png"
        video.write_bytes(b"deterministic-video-bytes")
        thumbnail.write_bytes(b"deterministic-thumbnail-bytes")
        return (
            CreatedAsset(
                asset_id="video",
                path=str(video),
                media_type="video/mp4",
                provenance="fixture://creator/video",
            ),
            CreatedAsset(
                asset_id="thumbnail",
                path=str(thumbnail),
                media_type="image/png",
                provenance="fixture://creator/thumbnail",
            ),
        )


def test_current_canonical_path_reaches_verified_without_publish(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    snapshots = SnapshotStore(tmp_path / "snapshots.db")
    transport = Transport()

    result = run_readonly_cycle(
        transport,
        journal,
        snapshots,
        [ScoutTopic("ambient", prior_score=0.9)],
        [],
        ScoutPolicy(query_budget=1, exploration_fraction=0),
        DiscoveryPolicy(max_candidates=5),
        observed_at="2026-10-07T01:00:00+00:00",
    )
    assert result.new_snapshots == 1

    refresh_tracked(
        snapshots,
        transport,
        journal,
        "2026-10-07T02:00:00+00:00",
    )
    refresh_tracked(
        snapshots,
        transport,
        journal,
        "2026-10-07T03:00:00+00:00",
    )

    report = analyze_intelligence(snapshots, journal, transport)
    assert len(report.ready) == 1
    signal = report.ready[0]
    assert signal.content_id == "target"
    assert signal.status == "READY"
    assert signal.version == "intelligence_pipeline.v4"
    assert signal.source_evidence_refs

    orchestrator = Orchestrator(journal)
    winner = orchestrator.choose_intelligence([signal])
    assert winner.content_id == "target"
    assert (
        orchestrator.states.current_state("youtube:target")
        is WorkflowState.EVIDENCE_COLLECTED
    )

    plan = CreativePlan(
        opportunity_id="youtube:target",
        platform="youtube",
        format="long-form",
        title="Original ambient concept",
        original=True,
        rights_confirmed=True,
        estimated_cost=1.0,
        id="plan-target",
    )
    gate = orchestrator.plan_selected(plan)
    assert gate.decision is Decision.ACCEPT
    assert (
        orchestrator.states.current_state("youtube:target")
        is WorkflowState.PLANNED
    )

    manifest = orchestrator.create_assets(
        plan,
        Creator(tmp_path),
    )
    assert [asset.asset_id for asset in manifest.assets] == [
        "video",
        "thumbnail",
    ]
    assert (
        orchestrator.states.current_state("youtube:target")
        is WorkflowState.ASSETS_READY
    )

    verification = orchestrator.verify_assets(plan)
    assert verification.decision is Decision.ACCEPT
    assert (
        orchestrator.states.current_state("youtube:target")
        is WorkflowState.VERIFIED
    )

    event_types = [event["event_type"] for event in journal.read_all()]
    assert "INTELLIGENCE_SELECTION" in event_types
    assert event_types.count("STATE_TRANSITION") == 5
    assert "PLAN_POLICY_DECISION" in event_types
    assert "DRY_RUN_PUBLICATION" not in event_types
    assert "PUBLICATION" not in event_types
    assert journal.verify_chain() is True
    assert snapshots.verify_integrity() is True

    reopened = Orchestrator(DecisionJournal(tmp_path / "journal.db"))
    assert (
        reopened.states.current_state("youtube:target")
        is WorkflowState.VERIFIED
    )
    latest = reopened.states.history("youtube:target")[-1]
    manifest_record = resolve_evidence(
        reopened.journal,
        latest.evidence.asset_manifest_refs[0],
    )
    verification_record = resolve_evidence(
        reopened.journal,
        latest.evidence.verification_ref,
    )
    assert manifest_record is not None
    assert manifest_record.receipt.evidence_type == "asset_manifest.v2"
    assert verification_record is not None
    assert verification_record.receipt.evidence_type == "verification.v1"
    assert verification_record.payload["decision"] == "ACCEPT"
    assert "copyright" not in verification_record.payload["verified_properties"]
    assert "originality" not in verification_record.payload["verified_properties"]
