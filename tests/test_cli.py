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
