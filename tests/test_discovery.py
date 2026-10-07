import pytest

from media_omega.discovery import DiscoveryItem, DiscoveryPolicy, select_candidates
from media_omega.youtube_http import YouTubeHTTPTransport


def item(content_id, title="valid title", evidence="api://youtube/x"):
    return DiscoveryItem("youtube", content_id, "creator", title, "2026-10-07T00:00:00Z", evidence)


def test_selection_deduplicates_and_filters_missing_evidence():
    result = select_candidates([item("a"), item("a"), item("b", evidence="")])
    assert [x.content_id for x in result] == ["a"]


def test_selection_respects_candidate_budget():
    result = select_candidates([item(str(i)) for i in range(10)], DiscoveryPolicy(max_candidates=3))
    assert len(result) == 3


def test_discovery_policy_rejects_excessive_budget():
    with pytest.raises(ValueError):
        DiscoveryPolicy(max_candidates=51).validate()


def test_youtube_discovery_normalizes_search_payload(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "secret")
    transport = YouTubeHTTPTransport()
    monkeypatch.setattr(transport, "_get_json", lambda endpoint, params: {
        "items": [{
            "id": {"videoId": "abc"},
            "snippet": {
                "channelId": "channel",
                "title": "A new opportunity",
                "publishedAt": "2026-10-07T00:00:00Z",
            },
        }]
    })
    rows = transport.discover_videos("ambient")
    assert rows[0]["content_id"] == "abc"
    assert rows[0]["evidence_ref"] == "api://youtube/search/abc"


def test_youtube_discovery_requires_query():
    with pytest.raises(ValueError):
        YouTubeHTTPTransport().discover_videos(" ")
