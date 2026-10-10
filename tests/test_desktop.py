import pytest

from media_omega import desktop


def test_find_popular_uses_readonly_env_token(monkeypatch):
    class FakeAPI:
        def __init__(self, access_token, *, api_key=""):
            assert access_token == "token"
            assert api_key == ""
        def get_popular_videos(self, *, region_code, max_results):
            assert (region_code, max_results) == ("TH", 10)
            return [{"title": "Top", "reuse_permission": "NOT_VERIFIED"}]
    monkeypatch.setenv("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", "token")
    monkeypatch.setattr(desktop, "YouTubeReadOnlyAPI", FakeAPI)
    assert desktop.find_popular("TH", 10)[0]["title"] == "Top"


def test_find_popular_requires_token(monkeypatch):
    monkeypatch.delenv("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", raising=False)
    with pytest.raises(ValueError, match="API key"):
        desktop.find_popular("TH", 10)


def test_render_blocked_without_rights(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop, "render_ambient_loop", lambda *a, **kw: calls.append(1))
    with pytest.raises(ValueError, match="rights"):
        desktop.create_local_video("in.mp4", "audio.mp3", "out.mp4", 60, False)
    assert calls == []


def test_render_calls_existing_engine_with_safe_options(monkeypatch):
    def fake_render(video, audio, output, **options):
        assert (video, audio, output) == ("mine.mp4", "mine.mp3", "done.mp4")
        assert options == {"duration_seconds": 60,
                           "video_crossfade_seconds": 0.7,
                           "video_loop_segment_seconds": 5.0,
                           "audio_crossfade_seconds": 0.15}
        return output
    monkeypatch.setattr(desktop, "render_ambient_loop", fake_render)
    assert desktop.create_local_video("mine.mp4", "mine.mp3", "done.mp4", 60, True) == "done.mp4"


def test_find_popular_api_key_from_desktop(monkeypatch):
    monkeypatch.delenv("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", raising=False)
    monkeypatch.delenv("MEDIA_OMEGA_YOUTUBE_API_KEY", raising=False)
    class FakeAPI:
        def __init__(self, access_token, *, api_key):
            assert access_token == ""
            assert api_key == "session-key"
        def get_popular_videos(self, *, region_code, max_results):
            assert (region_code, max_results) == ("TH", 10)
            return [{"title": "Music", "url": "https://www.youtube.com/watch?v=test", "views": 100}]
    monkeypatch.setattr(desktop, "YouTubeReadOnlyAPI", FakeAPI)
    assert desktop.find_popular("TH", 10, "session-key")[0]["title"] == "Music"
