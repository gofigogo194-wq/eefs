import pytest

from media_omega.baseline import (
    CreatorPerformanceSample,
    build_creator_baseline,
    relative_to_creator,
    sample_at,
)


def test_creator_baseline_normalizes_same_views_by_age():
    baseline = build_creator_baseline(
        "creator",
        [
            CreatorPerformanceSample(1000, 10),
            CreatorPerformanceSample(1000, 100),
            CreatorPerformanceSample(1000, 20),
        ],
    )
    assert baseline.median_views_per_hour == 50.0
    assert baseline.sample_count == 3
    assert baseline.confidence == 0.3
    assert baseline.version == "creator_baseline.v2"


def test_relative_performance_uses_target_age_too():
    baseline = build_creator_baseline(
        "creator",
        [
            CreatorPerformanceSample(1000, 10),
            CreatorPerformanceSample(1000, 20),
            CreatorPerformanceSample(1000, 40),
        ],
    )
    assert relative_to_creator(1000, 5, baseline) == 4.0


def test_zero_creator_velocity_fails_closed_instead_of_exploding():
    baseline = build_creator_baseline(
        "creator",
        [CreatorPerformanceSample(0, 10)] * 3,
    )
    assert relative_to_creator(100, 1, baseline) == 1.0


def test_sample_at_rejects_future_or_zero_age_without_inventing_rate():
    assert sample_at(
        100,
        "2026-10-07T12:00:00+00:00",
        "2026-10-07T12:00:00+00:00",
    ) is None
    assert sample_at(
        100,
        "2026-10-07T13:00:00+00:00",
        "2026-10-07T12:00:00+00:00",
    ) is None


def test_baseline_rejects_missing_or_invalid_history():
    with pytest.raises(ValueError):
        build_creator_baseline("creator", [])
    with pytest.raises(ValueError):
        build_creator_baseline(
            "creator",
            [CreatorPerformanceSample(-1, 1)],
        )
    with pytest.raises(ValueError):
        build_creator_baseline(
            "creator",
            [CreatorPerformanceSample(1, 0)],
        )
