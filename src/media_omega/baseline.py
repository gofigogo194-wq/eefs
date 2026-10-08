from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from statistics import median


_MIN_RATE_AGE_HOURS = 1.0 / 60.0


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class CreatorPerformanceSample:
    views: int
    age_hours: float

    @property
    def views_per_hour(self) -> float:
        if isinstance(self.views, bool) or not isinstance(self.views, int) or self.views < 0:
            raise ValueError("views must be a non-negative integer")
        if not isfinite(self.age_hours) or self.age_hours < _MIN_RATE_AGE_HOURS:
            raise ValueError("age_hours is too short or non-finite for reliable rate")
        return self.views / self.age_hours


@dataclass(frozen=True)
class CreatorBaseline:
    creator_id: str
    sample_count: int
    median_views_per_hour: float
    confidence: float
    version: str = "creator_baseline.v2"


def sample_at(
    views: int,
    published_at: str,
    observed_at: str,
) -> CreatorPerformanceSample | None:
    if isinstance(views, bool) or not isinstance(views, int) or views < 0:
        raise ValueError("views must be a non-negative integer")
    published = _time(published_at)
    observed = _time(observed_at)
    age_seconds = (observed - published).total_seconds()
    if age_seconds < 60.0:
        return None
    return CreatorPerformanceSample(
        views=views,
        age_hours=age_seconds / 3600.0,
    )


def build_creator_baseline(
    creator_id: str,
    history: list[CreatorPerformanceSample],
) -> CreatorBaseline:
    if not creator_id.strip():
        raise ValueError("creator_id is required")
    if not history:
        raise ValueError("creator baseline requires history")
    rates = [sample.views_per_hour for sample in history]
    confidence = min(len(rates) / 10.0, 1.0)
    return CreatorBaseline(
        creator_id=creator_id,
        sample_count=len(rates),
        median_views_per_hour=float(median(rates)),
        confidence=confidence,
    )


def relative_to_creator(
    views: int,
    age_hours: float,
    baseline: CreatorBaseline,
) -> float:
    target = CreatorPerformanceSample(views, age_hours).views_per_hour
    if baseline.median_views_per_hour <= 1e-6:
        return 1.0 if target > 0 else 0.0
    return target / baseline.median_views_per_hour
