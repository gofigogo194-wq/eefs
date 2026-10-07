from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class CreatorPerformanceSample:
    views: int
    age_hours: float

    @property
    def views_per_hour(self) -> float:
        if self.views < 0:
            raise ValueError("views cannot be negative")
        if self.age_hours <= 0:
            raise ValueError("age_hours must be positive")
        return self.views / self.age_hours


@dataclass(frozen=True)
class CreatorBaseline:
    creator_id: str
    sample_count: int
    median_views_per_hour: float
    confidence: float
    version: str = "creator_baseline.v2"


def build_creator_baseline(creator_id: str, history: list[CreatorPerformanceSample]) -> CreatorBaseline:
    if not creator_id:
        raise ValueError("creator_id is required")
    if not history:
        raise ValueError("creator baseline requires history")
    rates = [sample.views_per_hour for sample in history]
    confidence = min(len(rates) / 10.0, 1.0)
    return CreatorBaseline(creator_id, len(rates), float(median(rates)), confidence)


def relative_to_creator(views: int, age_hours: float, baseline: CreatorBaseline) -> float:
    target = CreatorPerformanceSample(views, age_hours).views_per_hour
    if baseline.median_views_per_hour <= 1e-6:
        return 1.0 if target > 0 else 0.0
    return target / baseline.median_views_per_hour
