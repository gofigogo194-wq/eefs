from media_omega.youtube_http import YouTubeHTTPTransport


class FakeTransport(YouTubeHTTPTransport):
    def _get_json(self, endpoint, params):
        assert endpoint == "videos"
        assert params["part"] == "snippet,statistics"
        return {"items": [{
            "id": "v1",
            "snippet": {"publishedAt": "2026-10-01T00:00:00Z"},
            "statistics": {"viewCount": "1234"},
        }]}


def test_video_details_returns_views_and_publication_time():
    result = FakeTransport().video_details(["v1"])
    assert result["v1"]["views"] == 1234
    assert result["v1"]["published_at"] == "2026-10-01T00:00:00Z"
