from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation
from media_omega.refresh import refresh_tracked
from media_omega.snapshots import SnapshotStore


def obs(cid, views=100):
    return ContentObservation(
        "youtube", cid, "creator", "2026-10-07T00:00:00+00:00",
        "2026-10-07T01:00:00+00:00", views, 1000, f"api://youtube/{cid}/1",
        "ambient sleep", "unknown",
    )


class Stats:
    def video_statistics(self, ids):
        return {x: 500 for x in ids if x != "missing"}


def test_refresh_adds_second_snapshot_for_tracked_videos(tmp_path):
    store = SnapshotStore(tmp_path / "s.db")
    store.append(obs("a"))
    store.append(obs("b"))
    result = refresh_tracked(
        store, Stats(), DecisionJournal(tmp_path / "j.db"),
        "2026-10-07T02:00:00+00:00",
    )
    assert result.tracked == 2
    assert result.new_snapshots == 2
    history = store.history("youtube", "a")
    assert len(history) == 2
    assert history[-1].discovery_query == "ambient sleep"
    assert history[-1].content_format == "unknown"
    assert history[-1].creator_baseline_views == 0.0


def test_refresh_tracks_missing_without_fabricating_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "s.db")
    store.append(obs("a"))
    store.append(obs("missing"))
    result = refresh_tracked(
        store, Stats(), DecisionJournal(tmp_path / "j.db"),
        "2026-10-07T02:00:00+00:00",
    )
    assert result.missing == 1
    assert len(store.history("youtube", "missing")) == 1
