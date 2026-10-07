import pytest

from media_omega.observations import ContentObservation
from media_omega.timeseries import momentum


def point(hour, views, content_id="x"):
    return ContentObservation(
        platform="youtube",
        content_id=content_id,
        creator_id="creator",
        published_at="2026-10-01T00:00:00+00:00",
        observed_at=f"2026-10-01T{hour:02d}:00:00+00:00",
        views=views,
        creator_baseline_views=1000,
        evidence_ref=f"fixture://{content_id}/{hour}",
    )


def test_momentum_detects_acceleration():
    signal = momentum([point(1, 100), point(2, 200), point(3, 500)])
    assert signal.previous_velocity == 100.0
    assert signal.latest_velocity == 300.0
    assert signal.acceleration_ratio == 3.0
    assert signal.sustained_growth is True


def test_momentum_rejects_too_few_samples():
    with pytest.raises(ValueError):
        momentum([point(1, 100), point(2, 200)])


def test_momentum_rejects_mixed_content():
    with pytest.raises(ValueError):
        momentum([point(1, 100), point(2, 200), point(3, 300, "other")])


def test_momentum_rejects_decreasing_cumulative_views():
    with pytest.raises(ValueError):
        momentum([point(1, 100), point(2, 90), point(3, 120)])
