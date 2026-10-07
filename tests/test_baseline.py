import pytest

from media_omega.baseline import build_creator_baseline, relative_to_creator


def test_creator_baseline_uses_median_against_old_viral_outlier():
    baseline = build_creator_baseline("creator", [900, 1000, 1100, 1200, 1000000])
    assert baseline.median_views == 1100.0
    assert baseline.sample_count == 5
    assert baseline.confidence == 0.5


def test_relative_performance_detects_breakout():
    baseline = build_creator_baseline("creator", [1800, 2000, 2200])
    assert relative_to_creator(50000, baseline) == 25.0


def test_baseline_confidence_caps_at_one():
    baseline = build_creator_baseline("creator", list(range(20)))
    assert baseline.confidence == 1.0


def test_baseline_rejects_missing_or_invalid_history():
    with pytest.raises(ValueError):
        build_creator_baseline("creator", [])
    with pytest.raises(ValueError):
        build_creator_baseline("creator", [100, -1])
