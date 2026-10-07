import pytest

from media_omega.observations import ContentObservation
from media_omega.sources import SourceRegistry, StaticObservationSource
from media_omega.youtube import YouTubeDataSource, YouTubePayloadError


def observation(ref="fixture://one"):
    return ContentObservation(
        "youtube", "video", "creator",
        "2026-10-01T00:00:00+00:00",
        "2026-10-01T01:00:00+00:00",
        100, 50, ref,
    )


def test_registry_collects_normalized_source():
    registry = SourceRegistry()
    registry.register(StaticObservationSource([observation()]))
    assert registry.collect()[0].content_id == "video"


def test_registry_rejects_duplicate_source():
    registry = SourceRegistry()
    registry.register(StaticObservationSource([]))
    with pytest.raises(ValueError):
        registry.register(StaticObservationSource([]))


def test_registry_rejects_unknown_provenance_scheme():
    registry = SourceRegistry()
    registry.register(StaticObservationSource([observation("opaque:123")]))
    with pytest.raises(ValueError):
        registry.collect()


def test_youtube_adapter_normalizes_injected_transport():
    def transport():
        return [{
            "content_id": "abc",
            "creator_id": "channel",
            "published_at": "2026-10-01T00:00:00+00:00",
            "observed_at": "2026-10-01T02:00:00+00:00",
            "views": 500,
            "creator_baseline_views": 100,
            "evidence_ref": "api://youtube/videos/abc",
        }]

    result = YouTubeDataSource(transport).fetch()
    assert len(result) == 1
    assert result[0].platform == "youtube"
    assert result[0].views_per_hour == 250


def test_youtube_adapter_fails_closed_on_missing_fields():
    with pytest.raises(YouTubePayloadError):
        YouTubeDataSource(lambda: [{"content_id": "abc"}]).fetch()
