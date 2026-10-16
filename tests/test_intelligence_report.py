from media_omega.intelligence_report import analyze_intelligence
from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation
from media_omega.snapshots import SnapshotStore


def obs(cid, creator, hour, views):
    return ContentObservation(
        "youtube", cid, creator, "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hour:02d}:00:00+00:00", views, 0,
        f"api://youtube/{cid}/{hour}",
    )


class Transport:
    def __init__(self, observed_at="2026-10-07T03:00:00+00:00"):
        self.observed_at = observed_at

    def channel_recent_video_ids(self, creator_id):
        return [f"{creator_id}-a", f"{creator_id}-b", f"{creator_id}-c"]

    def video_details(self, ids):
        return {
            x: {
                "views": 1000,
                "published_at": "2026-10-07T00:00:00+00:00",
                "observed_at": self.observed_at,
            } for x in ids
        }


def test_report_reads_persisted_history_and_ranks_ready_content(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    journal = DecisionJournal(tmp_path / "journal.db")
    for row in [
        obs("fast", "a", 1, 1000), obs("fast", "a", 2, 2000), obs("fast", "a", 3, 6000),
        obs("slow", "b", 1, 1000), obs("slow", "b", 2, 1500), obs("slow", "b", 3, 2100),
    ]:
        store.append(row)
    report = analyze_intelligence(store, journal, Transport())
    assert [x.content_id for x in report.ready] == ["fast", "slow"]
    assert report.insufficient_snapshot_history == ()
    assert report.insufficient_creator_history == ()
    assert report.unreliable_creator_baseline == ()


def test_report_separates_short_snapshot_history(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    journal = DecisionJournal(tmp_path / "journal.db")
    store.append(obs("short", "a", 1, 100))
    store.append(obs("short", "a", 2, 200))
    report = analyze_intelligence(store, journal, Transport())
    assert report.ready == ()
    assert report.insufficient_snapshot_history == ("short",)


def test_report_separates_stale_creator_baseline(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    journal = DecisionJournal(tmp_path / "journal.db")
    for row in [obs("stale", "a", 1, 1000), obs("stale", "a", 2, 2000), obs("stale", "a", 3, 5000)]:
        store.append(row)
    report = analyze_intelligence(store, journal, Transport("2026-10-07T05:00:00+00:00"))
    assert report.ready == ()
    assert report.unreliable_creator_baseline == ("stale",)


def test_one_bad_history_does_not_block_other_ready_content(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    journal = DecisionJournal(tmp_path / "journal.db")
    for row in [
        obs("good", "g", 1, 1000),
        obs("good", "g", 2, 2000),
        obs("good", "g", 3, 5000),
        obs("bad", "b", 1, 1000),
        obs("bad", "b", 2, 900),
        obs("bad", "b", 3, 1200),
    ]:
        store.append(row)

    report = analyze_intelligence(store, journal, Transport())
    assert [x.content_id for x in report.ready] == ["good"]
    assert report.unreliable_history == ("bad",)
