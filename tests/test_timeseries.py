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


def test_zero_previous_velocity_does_not_create_infinite_acceleration():
    history = [
        point(0, 100),
        point(1, 100),
        point(2, 200),
    ]
    signal = momentum(history)
    assert signal.previous_velocity == 0.0
    assert signal.latest_velocity == 100.0
    assert signal.acceleration_ratio == 1.0
    assert signal.sustained_growth is False
    assert signal.formula_version == "momentum.v2"


def test_momentum_rejects_sub_minute_sampling_noise():
    history = [
        ContentObservation("youtube", "x", "creator", "2026-10-01T00:00:00+00:00",
                           "2026-10-01T01:00:00+00:00", 100, 1000, "fixture://x/1"),
        ContentObservation("youtube", "x", "creator", "2026-10-01T00:00:00+00:00",
                           "2026-10-01T01:00:30+00:00", 101, 1000, "fixture://x/2"),
        ContentObservation("youtube", "x", "creator", "2026-10-01T00:00:00+00:00",
                           "2026-10-01T01:01:00+00:00", 103, 1000, "fixture://x/3"),
    ]
    with pytest.raises(ValueError, match="too short"):
        momentum(history)
