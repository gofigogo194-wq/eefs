from datetime import datetime

import pytest

from media_omega.youtube_http import YouTubeHTTPTransport, YouTubePayloadError


class FakeTransport(YouTubeHTTPTransport):
    def _get_json(self, endpoint, params):
        assert endpoint == "videos"
        assert params["part"] == "snippet,statistics"
        return {"items": [{
            "id": "v1",
            "snippet": {"publishedAt": "2026-10-01T00:00:00Z"},
            "statistics": {"viewCount": "1234"},
        }]}


def test_video_details_returns_views_publication_and_observation_time():
    result = FakeTransport().video_details(["v1"])
    assert result["v1"]["views"] == 1234
    assert result["v1"]["published_at"] == "2026-10-01T00:00:00Z"
    observed = datetime.fromisoformat(result["v1"]["observed_at"])
    assert observed.tzinfo is not None


class PayloadTransport(YouTubeHTTPTransport):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    def _get_json(self, endpoint, params):
        return self.payload


def test_video_payload_items_must_be_list():
    with pytest.raises(YouTubePayloadError, match="list of objects"):
        PayloadTransport({"items": None}).video_statistics(["v1"])


def test_statistics_rejects_unexpected_or_duplicate_ids():
    with pytest.raises(YouTubePayloadError, match="unexpected id"):
        PayloadTransport({
            "items": [{"id": "other", "statistics": {"viewCount": "1"}}]
        }).video_statistics(["v1"])

    with pytest.raises(YouTubePayloadError, match="duplicate id"):
        PayloadTransport({
            "items": [
                {"id": "v1", "statistics": {"viewCount": "1"}},
                {"id": "v1", "statistics": {"viewCount": "1"}},
            ]
        }).video_statistics(["v1"])


def test_statistics_rejects_negative_views():
    with pytest.raises(YouTubePayloadError, match="cannot be negative"):
        PayloadTransport({
            "items": [{"id": "v1", "statistics": {"viewCount": "-1"}}]
        }).video_statistics(["v1"])


def test_video_details_rejects_naive_publication_timestamp():
    with pytest.raises(YouTubePayloadError, match="timezone-aware"):
        PayloadTransport({
            "items": [{
                "id": "v1",
                "snippet": {"publishedAt": "2026-10-01T00:00:00"},
                "statistics": {"viewCount": "1"},
            }]
        }).video_details(["v1"])
