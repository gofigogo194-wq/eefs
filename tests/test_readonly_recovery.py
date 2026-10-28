import sqlite3

import pytest

from media_omega.discovery import DiscoveryPolicy
from media_omega.intelligence_report import analyze_intelligence
from media_omega.memory import DecisionJournal
from media_omega.orchestrator import Orchestrator
from media_omega.observations import ContentObservation
from media_omega.refresh import refresh_tracked
from media_omega.runtime import run_readonly_cycle
from media_omega.scout import ScoutPolicy, ScoutTopic
from media_omega.snapshots import SnapshotStore
from media_omega.state_machine import WorkflowState


class DiscoveryTransport:
    def __init__(self, views=1000):
        self.views = views

    def discover_videos(self, query):
        return [{
            "content_id": "target",
            "creator_id": "creator",
            "title": "Clear opportunity",
            "published_at": "2026-10-07T00:00:00+00:00",
            "evidence_ref": "api://youtube/search/target",
        }]

    def video_statistics(self, ids):
        return {content_id: self.views for content_id in ids}


class IntelligenceTransport:
    def __init__(self, views):
        self.views = views

    def video_statistics(self, ids):
        return {content_id: self.views for content_id in ids}

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


def scout_once(journal, snapshots, transport, observed_at):
    return run_readonly_cycle(
        transport,
        journal,
        snapshots,
        [ScoutTopic("ambient", prior_score=0.9)],
        [],
        ScoutPolicy(query_budget=1, exploration_fraction=0),
        DiscoveryPolicy(max_candidates=5),
        observed_at=observed_at,
    )


def test_same_readonly_observation_replay_is_idempotent(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    snapshots = SnapshotStore(tmp_path / "snapshots.db")
    transport = DiscoveryTransport(1000)

    first = scout_once(
        journal,
        snapshots,
        transport,
        "2026-10-07T01:00:00+00:00",
    )
    second = scout_once(
        journal,
        snapshots,
        transport,
        "2026-10-07T01:00:00+00:00",
    )

    assert first.new_snapshots == 1
    assert second.new_snapshots == 0
    assert snapshots.count() == 1
    assert snapshots.verify_integrity() is True
    assert journal.verify_chain() is True


def test_restart_reopens_state_and_continues_to_same_intelligence_boundary(tmp_path):
    journal_path = tmp_path / "journal.db"
    snapshot_path = tmp_path / "snapshots.db"

    journal = DecisionJournal(journal_path)
    snapshots = SnapshotStore(snapshot_path)
    scout_once(
        journal,
        snapshots,
        DiscoveryTransport(1000),
        "2026-10-07T01:00:00+00:00",
    )

    # Simulate a process restart: discard objects and reopen only persisted state.
    journal = DecisionJournal(journal_path)
    snapshots = SnapshotStore(snapshot_path)
    refresh_tracked(
        snapshots,
        IntelligenceTransport(2000),
        journal,
        "2026-10-07T02:00:00+00:00",
    )

    journal = DecisionJournal(journal_path)
    snapshots = SnapshotStore(snapshot_path)
    refresh_tracked(
        snapshots,
        IntelligenceTransport(5000),
        journal,
        "2026-10-07T03:00:00+00:00",
    )

    report = analyze_intelligence(
        snapshots,
        journal,
        IntelligenceTransport(5000),
    )
    assert [signal.content_id for signal in report.ready] == ["target"]

    winner = Orchestrator(journal).choose_intelligence(list(report.ready))
    assert winner.content_id == "target"

    reopened = Orchestrator(DecisionJournal(journal_path))
    assert (
        reopened.states.current_state("youtube:target")
        is WorkflowState.EVIDENCE_COLLECTED
    )
    assert SnapshotStore(snapshot_path).verify_integrity() is True
    assert reopened.journal.verify_chain() is True


def test_partial_refresh_does_not_fabricate_missing_video_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    journal = DecisionJournal(tmp_path / "journal.db")
    for content_id in ("a", "b"):
        store.append(ContentObservation(
            "youtube",
            content_id,
            "creator",
            "2026-10-07T00:00:00+00:00",
            "2026-10-07T01:00:00+00:00",
            100,
            0,
            f"fixture://{content_id}/1",
        ))

    class PartialTransport:
        def video_statistics(self, ids):
            return {"a": 200, "unexpected": 999}

    result = refresh_tracked(
        store,
        PartialTransport(),
        journal,
        "2026-10-07T02:00:00+00:00",
    )

    assert result.tracked == 2
    assert result.returned == 1
    assert result.missing == 1
    assert result.new_snapshots == 1
    assert len(store.history("youtube", "a")) == 2
    assert len(store.history("youtube", "b")) == 1


def test_corrupt_snapshot_store_refuses_restart(tmp_path):
    path = tmp_path / "snapshots.db"
    store = SnapshotStore(path)
    store.append(ContentObservation(
        "youtube",
        "target",
        "creator",
        "2026-10-07T00:00:00+00:00",
        "2026-10-07T01:00:00+00:00",
        100,
        0,
        "fixture://target/1",
    ))

    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER snapshots_append_only_update")
        payload = db.execute(
            "SELECT payload FROM snapshots WHERE content_id='target'"
        ).fetchone()[0]
        db.execute(
            "UPDATE snapshots SET payload=? WHERE content_id='target'",
            (payload.replace('"views":100', '"views":999'),),
        )

    with pytest.raises(RuntimeError, match="hash"):
        SnapshotStore(path)
