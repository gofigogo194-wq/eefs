from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation
from media_omega.report import analyze_tracked
from media_omega.snapshots import SnapshotStore


def obs(cid, hour, views):
    return ContentObservation(
        "youtube", cid, "creator", "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hour:02d}:00:00+00:00", views, 1000,
        f"api://youtube/{cid}/{hour}",
    )


def test_report_refuses_momentum_with_only_two_snapshots(tmp_path):
    store = SnapshotStore(tmp_path / "s.db")
    store.append(obs("a", 1, 100))
    store.append(obs("a", 2, 200))
    report = analyze_tracked(store, DecisionJournal(tmp_path / "j.db"))
    assert report.ready == ()
    assert report.insufficient_history == ("a",)


def test_report_ranks_ready_videos_by_acceleration(tmp_path):
    store = SnapshotStore(tmp_path / "s.db")
    for point in [obs("fast", 1, 100), obs("fast", 2, 200), obs("fast", 3, 500),
                  obs("slow", 1, 100), obs("slow", 2, 200), obs("slow", 3, 310)]:
        store.append(point)
    report = analyze_tracked(store, DecisionJournal(tmp_path / "j.db"))
    assert [x.content_id for x in report.ready] == ["fast", "slow"]
    assert report.ready[0].acceleration_ratio == 3.0
    assert report.ready[0].sustained_growth is True
