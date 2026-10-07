from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class CreatorBaseline:
    creator_id: str
    sample_count: int
    median_views: float
    confidence: float
    version: str = "creator_baseline.v1"


def build_creator_baseline(creator_id: str, historical_views: list[int]) -> CreatorBaseline:
    if not creator_id:
        raise ValueError("creator_id is required")
    clean = [int(v) for v in historical_views if int(v) >= 0]
    if len(clean) != len(historical_views):
        raise ValueError("historical views cannot be negative")
    if not clean:
        raise ValueError("creator baseline requires history")
    # Confidence means evidence sufficiency, not probability of success.
    confidence = min(len(clean) / 10.0, 1.0)
    return CreatorBaseline(
        creator_id=creator_id,
        sample_count=len(clean),
        median_views=float(median(clean)),
        confidence=confidence,
    )


def relative_to_creator(views: int, baseline: CreatorBaseline) -> float:
    if views < 0:
        raise ValueError("views cannot be negative")
    denominator = max(baseline.median_views, 1.0)
    return views / denominator
