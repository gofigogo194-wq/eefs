import json
import sqlite3

import pytest

from media_omega.cli import _refresh
from media_omega.observations import ContentObservation
from media_omega.snapshots import (
    SnapshotStore,
    _canonical_payload,
    _semantic_digest,
    _sha256_text,
)
from media_omega.timeseries import momentum
from media_omega.youtube_http import YouTubeHTTPTransport, YouTubePayloadError


def observation(
    *,
    creator_id="creator",
    published_at="2026-10-07T00:00:00+00:00",
    observed_at="2026-10-07T01:00:00+00:00",
    views=100,
):
    return ContentObservation(
        "youtube",
        "target",
        creator_id,
        published_at,
        observed_at,
        views,
        0,
        "fixture://target",
    )


def test_snapshot_store_creates_missing_parent_directory(tmp_path):
    path = tmp_path / "nested" / "state" / "snapshots.db"
    store = SnapshotStore(path)

    assert path.is_file()
    assert store.verify_integrity() is True


@pytest.mark.parametrize(
    "changed",
    [
        observation(
            creator_id="other-creator",
            observed_at="2026-10-07T02:00:00+00:00",
            views=200,
        ),
        observation(
            published_at="2026-10-06T23:00:00+00:00",
            observed_at="2026-10-07T02:00:00+00:00",
            views=200,
        ),
    ],
)
def test_snapshot_store_rejects_cross_snapshot_identity_drift(tmp_path, changed):
    store = SnapshotStore(tmp_path / "snapshots.db")
    store.append(observation())

    with pytest.raises(RuntimeError, match="identity drift"):
        store.append(changed)

    assert store.count() == 1


def test_snapshot_restart_detects_preexisting_identity_drift(tmp_path):
    path = tmp_path / "snapshots.db"
    store = SnapshotStore(path)
    store.append(observation())

    forged = observation(
        creator_id="forged-creator",
        observed_at="2026-10-07T02:00:00+00:00",
        views=200,
    )
    canonical = _canonical_payload(forged)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO snapshots("
            "platform,content_id,observed_at,payload,payload_sha256,semantic_sha256"
            ") VALUES(?,?,?,?,?,?)",
            (
                forged.platform,
                forged.content_id,
                canonical["observed_at"],
                payload,
                _sha256_text(payload),
                _semantic_digest(canonical),
            ),
        )

    with pytest.raises(RuntimeError, match="identity drift"):
        SnapshotStore(path)


def test_momentum_rejects_identity_drift_even_without_snapshot_store():
    history = [
        observation(
            observed_at="2026-10-07T01:00:00+00:00",
            views=100,
        ),
        observation(
            observed_at="2026-10-07T02:00:00+00:00",
            views=200,
        ),
        observation(
            creator_id="other-creator",
            observed_at="2026-10-07T03:00:00+00:00",
            views=400,
        ),
    ]

    with pytest.raises(ValueError, match="identity drift"):
        momentum(history)


def test_refresh_refuses_incomplete_state_without_journal(tmp_path):
    root = tmp_path / "state"
    SnapshotStore(root / "snapshots.db")

    with pytest.raises(FileNotFoundError, match="complete state"):
        _refresh(str(root))

    assert not (root / "journal.db").exists()


class PayloadTransport(YouTubeHTTPTransport):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    def _get_json(self, endpoint, params):
        return self.payload


def test_discovery_rejects_null_identity_instead_of_stringifying_it():
    transport = PayloadTransport({
        "items": [{
            "id": {"videoId": None},
            "snippet": {
                "channelId": "channel",
                "title": "Valid title",
                "publishedAt": "2026-10-07T00:00:00Z",
            },
        }],
    })

    with pytest.raises(YouTubePayloadError, match="videoId"):
        transport.discover_videos("ambient")


def test_channel_history_rejects_malformed_identity_object():
    transport = PayloadTransport({"items": [{"id": None}]})

    with pytest.raises(YouTubePayloadError, match="channel payload"):
        transport.channel_recent_video_ids("creator")


def test_statistics_rejects_null_result_id():
    transport = PayloadTransport({
        "items": [{"id": None, "statistics": {"viewCount": "1"}}],
    })

    with pytest.raises(YouTubePayloadError, match="id"):
        transport.video_statistics(["v1"])


def test_observation_rejects_non_string_cohort_fields():
    bad = ContentObservation(
        "youtube",
        "target",
        "creator",
        "2026-10-07T00:00:00+00:00",
        "2026-10-07T01:00:00+00:00",
        100,
        0,
        "fixture://target",
        discovery_query=123,
    )
    with pytest.raises(ValueError, match="discovery_query"):
        bad.validate()


def test_discovery_filters_non_string_identity_values():
    from media_omega.discovery import DiscoveryItem, select_candidates

    malformed = DiscoveryItem(
        platform="youtube",
        content_id=None,
        creator_id="creator",
        title="Valid title",
        published_at="2026-10-07T00:00:00Z",
        evidence_ref="fixture://evidence",
    )
    assert select_candidates([malformed]) == []


def test_transport_wraps_invalid_json_as_payload_error(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fixture-key")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"{not-json"

    monkeypatch.setattr(
        "media_omega.youtube_http.urlopen",
        lambda request, timeout: Response(),
    )

    with pytest.raises(YouTubePayloadError, match="invalid JSON"):
        YouTubeHTTPTransport().video_statistics(["v1"])
