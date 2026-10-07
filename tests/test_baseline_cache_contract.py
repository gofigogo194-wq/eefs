import pytest

from media_omega.baseline_cache import CreatorBaselineCache


class NoopTransport:
    def channel_recent_video_ids(self, creator_id):
        raise AssertionError("transport must not be called for invalid input")

    def video_statistics(self, ids):
        raise AssertionError("transport must not be called for invalid input")


def test_cache_rejects_non_positive_minimum_samples():
    with pytest.raises(ValueError, match="minimum_samples"):
        CreatorBaselineCache(NoopTransport(), minimum_samples=0)


def test_cache_rejects_empty_creator_before_transport():
    cache = CreatorBaselineCache(NoopTransport())
    with pytest.raises(ValueError, match="creator_id"):
        cache.get("   ")
