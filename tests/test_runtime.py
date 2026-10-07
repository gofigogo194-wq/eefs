from media_omega.discovery import DiscoveryPolicy
from media_omega.memory import DecisionJournal
from media_omega.runtime import run_readonly_cycle
from media_omega.scout import ScoutPolicy, ScoutTopic
from media_omega.snapshots import SnapshotStore


class Transport:
    def discover_videos(self, query):
        return [{
            "content_id": f"id-{query}",
            "creator_id": "creator",
            "title": f"Video {query}",
            "published_at": "2026-10-07T00:00:00+00:00",
            "evidence_ref": f"api://youtube/search/id-{query}",
        }]

    def video_statistics(self, ids):
        return {video_id: 1234 for video_id in ids}


def test_full_readonly_cycle_persists_real_shape_snapshots(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    snapshots = SnapshotStore(tmp_path / "snapshots.db")
    result = run_readonly_cycle(
        Transport(), journal, snapshots,
        [ScoutTopic("ambient", prior_score=0.9)],
        ["robotics"],
        ScoutPolicy(query_budget=2, exploration_fraction=0.5),
        DiscoveryPolicy(max_candidates=10),
    )
    assert result.mode == "read-only"
    assert result.discovered == 2
    assert result.selected == 2
    assert result.observations == 2
    assert result.new_snapshots == 2
    assert snapshots.count() == 2
    assert journal.read_all()[-1]["event_type"] == "READONLY_CYCLE_RESULT"
