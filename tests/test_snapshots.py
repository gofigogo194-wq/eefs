import json
import sqlite3

import pytest

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


def test_same_instant_with_different_offsets_is_idempotent(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    a = ContentObservation(
        "youtube", "same-instant", "creator",
        "2026-10-07T00:00:00+00:00", "2026-10-07T13:00:00+07:00",
        100, 1000, "fixture://a",
    )
    b = ContentObservation(
        "youtube", "same-instant", "creator",
        "2026-10-07T00:00:00+00:00", "2026-10-07T06:00:00+00:00",
        100, 1000, "fixture://b",
    )
    assert store.append(a) is True
    assert store.append(b) is False
    assert store.count() == 1


def test_same_identity_with_different_semantics_is_a_conflict(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    assert store.append(point(1, 100)) is True
    with pytest.raises(RuntimeError, match="identity conflict"):
        store.append(point(1, 200))


def test_snapshot_rows_are_database_append_only(tmp_path):
    path = tmp_path / "snapshots.db"
    store = SnapshotStore(path)
    store.append(point(1, 100))

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute("UPDATE snapshots SET content_id='mutated'")

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute("DELETE FROM snapshots")

    assert store.verify_integrity() is True


def test_direct_unhashed_snapshot_insert_is_blocked(tmp_path):
    path = tmp_path / "snapshots.db"
    SnapshotStore(path)
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="hash fields"):
            db.execute(
                "INSERT INTO snapshots(platform,content_id,observed_at,payload) "
                "VALUES(?,?,?,?)",
                (
                    "youtube",
                    "x",
                    "2026-10-07T01:00:00+00:00",
                    "{}",
                ),
            )


def test_snapshot_integrity_detects_payload_tamper(tmp_path):
    path = tmp_path / "snapshots.db"
    store = SnapshotStore(path)
    store.append(point(1, 100))
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER snapshots_append_only_update")
        payload = db.execute(
            "SELECT payload FROM snapshots LIMIT 1"
        ).fetchone()[0]
        value = json.loads(payload)
        value["views"] = 999
        db.execute(
            "UPDATE snapshots SET payload=?",
            (json.dumps(value, sort_keys=True, separators=(",", ":")),),
        )

    assert store.verify_integrity() is False
    with pytest.raises(RuntimeError, match="hash mismatch"):
        store.history("youtube", "video")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        store.count()


def test_legacy_snapshot_store_migrates_hashes_without_losing_data(tmp_path):
    path = tmp_path / "legacy-snapshots.db"
    observation = point(1, 100)
    payload = json.dumps(
        {
            "platform": observation.platform,
            "content_id": observation.content_id,
            "creator_id": observation.creator_id,
            "published_at": observation.published_at,
            "observed_at": observation.observed_at,
            "views": observation.views,
            "creator_baseline_views": observation.creator_baseline_views,
            "evidence_ref": observation.evidence_ref,
            "discovery_query": observation.discovery_query,
            "content_format": observation.content_format,
        },
        sort_keys=True,
    )
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE snapshots (
                platform TEXT NOT NULL,
                content_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (platform, content_id, observed_at)
            )
        """)
        db.execute(
            "INSERT INTO snapshots(platform,content_id,observed_at,payload) "
            "VALUES(?,?,?,?)",
            (
                "youtube",
                "video",
                "2026-10-07T01:00:00+00:00",
                payload,
            ),
        )

    store = SnapshotStore(path)
    assert store.verify_integrity() is True
    assert store.count() == 1
    assert store.history("youtube", "video")[0].views == 100


def test_idempotent_append_cannot_hide_existing_payload_tamper(tmp_path):
    path = tmp_path / "snapshots.db"
    store = SnapshotStore(path)
    original = point(1, 100)
    assert store.append(original) is True

    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER snapshots_append_only_update")
        payload = db.execute(
            "SELECT payload FROM snapshots LIMIT 1"
        ).fetchone()[0]
        value = json.loads(payload)
        value["evidence_ref"] = "fixture://tampered"
        db.execute(
            "UPDATE snapshots SET payload=?",
            (json.dumps(value, sort_keys=True, separators=(",", ":")),),
        )

    with pytest.raises(RuntimeError, match="hash mismatch"):
        store.append(original)
