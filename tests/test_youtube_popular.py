import pytest

from media_omega.youtube_api_readonly import YouTubeReadOnlyAPI


class FakeOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n=-1):
                return b'{"items":[{"id":"abc123","snippet":{"title":"Popular","channelId":"channel1"},"statistics":{"viewCount":"125000"}}]}'
        return Response()


def test_popular_chart_returns_simple_shortlist():
    opener = FakeOpener()
    api = YouTubeReadOnlyAPI("token", opener=opener)
    items = api.get_popular_videos(region_code="TH", max_results=5)
    assert items == [{
        "video_id": "abc123",
        "url": "https://www.youtube.com/watch?v=abc123",
        "title": "Popular",
        "channel_id": "channel1",
        "views": 125000,
        "reuse_permission": "NOT_VERIFIED",
    }]
    req = opener.requests[0]
    assert req.get_method() == "GET"
    assert "chart=mostPopular" in req.full_url
    assert "regionCode=TH" in req.full_url


@pytest.mark.parametrize("region,n", [("Thailand", 10), ("TH", 0), ("TH", 51), ("", 5)])
def test_popular_chart_fails_bad_arguments(region, n):
    with pytest.raises(ValueError):
        YouTubeReadOnlyAPI("token", opener=FakeOpener()).get_popular_videos(
            region_code=region, max_results=n,
        )
