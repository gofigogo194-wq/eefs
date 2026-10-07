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
