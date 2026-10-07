from media_omega.observations import ContentObservation
from media_omega.snapshots import SnapshotStore
from media_omega.timeseries import momentum


def point(hour, views):
    return ContentObservation(
        "youtube", "video", "creator",
        "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hour:02d}:00:00+00:00",
        views, 1000, f"api://youtube/video/{hour}",
    )


def test_snapshot_store_persists_ordered_history(tmp_path):
    path = tmp_path / "snapshots.db"
    store = SnapshotStore(path)
    store.append(point(3, 900))
    store.append(point(1, 100))
    store.append(point(2, 300))

    reopened = SnapshotStore(path)
    history = reopened.history("youtube", "video")
    assert [x.views for x in history] == [100, 300, 900]
    assert reopened.count() == 3


def test_snapshot_store_is_idempotent_for_same_observation_time(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    assert store.append(point(1, 100)) is True
    assert store.append(point(1, 100)) is False
    assert store.count() == 1


def test_persisted_history_drives_momentum_engine(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    for observation in [point(1, 100), point(2, 300), point(3, 900)]:
        store.append(observation)
    signal = momentum(store.history("youtube", "video"))
    assert signal.previous_velocity == 200.0
    assert signal.latest_velocity == 600.0
    assert signal.acceleration_ratio == 3.0
    assert signal.sustained_growth is True


def test_latest_uses_absolute_time_not_lexical_offset_order(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    earlier = ContentObservation(
        "youtube", "offset-video", "creator",
        "2026-10-07T00:00:00+00:00", "2026-10-07T12:30:00+07:00",
        100, 1000, "fixture://earlier",
    )
    later = ContentObservation(
        "youtube", "offset-video", "creator",
        "2026-10-07T00:00:00+00:00", "2026-10-07T06:00:00+00:00",
        200, 1000, "fixture://later",
    )
    store.append(earlier)
    store.append(later)
    assert store.latest("youtube")[0].views == 200
