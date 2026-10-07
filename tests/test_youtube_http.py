import pytest

from media_omega.youtube_http import YouTubeHTTPTransport, YouTubeReadOnlyConfig


def test_config_fails_closed_without_api_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        YouTubeReadOnlyConfig().api_key()


def test_config_reads_key_from_environment(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "secret-test-value")
    assert YouTubeReadOnlyConfig().api_key() == "secret-test-value"


def test_statistics_rejects_more_than_fifty_ids(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "not-used")
    transport = YouTubeHTTPTransport()
    with pytest.raises(ValueError):
        transport.video_statistics([f"id-{i}" for i in range(51)])


def test_statistics_empty_input_does_not_require_credentials(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    transport = YouTubeHTTPTransport()
    assert transport.video_statistics([]) == {}


def test_channel_id_is_required():
    with pytest.raises(ValueError):
        YouTubeHTTPTransport().channel_recent_video_ids("")
