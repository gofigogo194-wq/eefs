import json

from media_omega import cli


class FakeTransport:
    def video_statistics(self, ids):
        return {ids[0]: 12345}


def test_youtube_probe_reports_read_only_result(monkeypatch, capsys):
    monkeypatch.setattr(cli, "YouTubeHTTPTransport", lambda: FakeTransport())
    code = cli.main(["youtube-probe", "--video-id", "abc"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload == {
        "ok": True,
        "mode": "read-only",
        "video_id": "abc",
        "views": 12345,
    }


def test_scout_cli_runs_persistent_cycle(monkeypatch, tmp_path, capsys):
    from media_omega import cli

    class FakeTransport:
        def discover_videos(self, query):
            return [{
                "content_id": "abc",
                "creator_id": "creator",
                "title": "Emerging video",
                "published_at": "2026-10-07T00:00:00+00:00",
                "evidence_ref": "api://youtube/search/abc",
            }]
        def video_statistics(self, ids):
            return {"abc": 1234}

    monkeypatch.setattr(cli, "YouTubeHTTPTransport", FakeTransport)
    code = cli.main(["scout", "--query", "ambient", "--state-dir", str(tmp_path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "read-only"
    assert payload["observations"] == 1
    assert payload["snapshot_total"] == 1


def test_refresh_cli_reuses_persistent_state(monkeypatch, tmp_path, capsys):
    from media_omega import cli
    from media_omega.observations import ContentObservation
    from media_omega.snapshots import SnapshotStore

    store = SnapshotStore(tmp_path / "snapshots.db")
    store.append(ContentObservation(
        "youtube", "abc", "creator",
        "2026-10-07T00:00:00+00:00",
        "2026-10-07T01:00:00+00:00",
        100, 1000, "api://youtube/abc/1",
    ))

    class FakeTransport:
        def video_statistics(self, ids):
            return {"abc": 250}

    monkeypatch.setattr(cli, "YouTubeHTTPTransport", FakeTransport)
    code = cli.main(["refresh", "--state-dir", str(tmp_path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tracked"] == 1
    assert payload["new_snapshots"] == 1
    assert payload["snapshot_total"] == 2


def test_intelligence_cli_with_short_history_avoids_live_creator_fetch(tmp_path, capsys, monkeypatch):
    from media_omega import cli
    from media_omega.observations import ContentObservation
    from media_omega.snapshots import SnapshotStore

    store = SnapshotStore(tmp_path / "snapshots.db")
    for hour, views in [(1, 100), (2, 200)]:
        store.append(ContentObservation(
            "youtube", "abc", "creator",
            "2026-10-07T00:00:00+00:00",
            f"2026-10-07T{hour:02d}:00:00+00:00",
            views, 1, f"api://youtube/abc/{hour}",
        ))

    class ForbiddenTransport:
        def channel_recent_video_ids(self, creator_id):
            raise AssertionError("creator API must not be called before snapshot gate")
        def video_statistics(self, ids):
            raise AssertionError("statistics API must not be called before snapshot gate")

    monkeypatch.setattr(cli, "YouTubeHTTPTransport", lambda: ForbiddenTransport())
    code = cli.main(["intelligence", "--state-dir", str(tmp_path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "read-only"
    assert payload["ready_count"] == 0
    assert payload["insufficient_snapshot_history_count"] == 1
    assert payload["signals"] == []
