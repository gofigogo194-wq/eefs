import json

import pytest

from media_omega import cli


def test_popular_cli_uses_readonly_token_env(monkeypatch, capsys):
    class FakeAPI:
        def __init__(self, token):
            assert token == "fake-memory-token"
        def get_popular_videos(self, *, region_code, max_results):
            assert (region_code, max_results) == ("TH", 2)
            return [{"video_id": "v1", "reuse_permission": "NOT_VERIFIED"}]
    monkeypatch.setenv("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", "fake-memory-token")
    monkeypatch.setattr("media_omega.youtube_api_readonly.YouTubeReadOnlyAPI", FakeAPI)
    assert cli.main(["popular", "--region", "TH", "--count", "2"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "READ_ONLY"
    assert output["videos"][0]["reuse_permission"] == "NOT_VERIFIED"
    assert "fake-memory-token" not in json.dumps(output)


def test_popular_cli_requires_token(monkeypatch):
    monkeypatch.delenv("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", raising=False)
    with pytest.raises(ValueError, match="READONLY_TOKEN"):
        cli.main(["popular"])


def test_render_cli_blocks_without_rights(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("media_omega.ambient_renderer.render_ambient_loop",
                        lambda *a, **kw: calls.append((a,kw)))
    with pytest.raises(ValueError, match="confirm rights"):
        cli.main(["render", "--video", "clip.mp4", "--audio", "track.wav",
                  "--output", str(tmp_path / "out.mp4"), "--duration", "10"])
    assert not calls


def test_render_cli_uses_local_inputs_not_remote(monkeypatch, tmp_path, capsys):
    def fake_render(video, audio, output, **options):
        assert (video, audio) == ("owned.mp4", "licensed.mp3")
        assert options["duration_seconds"] == 12
        assert options["video_crossfade_seconds"] == 0.2
        assert options["audio_crossfade_seconds"] == 0.1
        return output
    monkeypatch.setattr("media_omega.ambient_renderer.render_ambient_loop", fake_render)
    output = str(tmp_path / "out.mp4")
    assert cli.main(["render", "--video", "owned.mp4", "--audio", "licensed.mp3",
                     "--output", output, "--duration", "12", "--video-fade", "0.2",
                     "--audio-fade", "0.1", "--rights-confirmed"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "mode": "LOCAL_RENDER", "published": False, "output": output}
