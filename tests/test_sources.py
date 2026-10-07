import pytest

from media_omega.observations import ContentObservation
from media_omega.sources import SourceRegistry, StaticObservationSource


def observation(ref="fixture://one"):
    return ContentObservation(
        "youtube", "video", "creator",
        "2026-10-01T00:00:00+00:00",
        "2026-10-01T01:00:00+00:00",
        100, 0, ref,
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
