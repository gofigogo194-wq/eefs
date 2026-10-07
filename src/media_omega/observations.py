from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log1p
from statistics import median


@dataclass(frozen=True)
class ContentObservation:
    platform: str
    content_id: str
    creator_id: str
    published_at: str
    observed_at: str
    views: int
    creator_baseline_views: float
    evidence_ref: str
    discovery_query: str = ""
    content_format: str = "unknown"

    def validate(self) -> None:
        if not self.platform.strip() or not self.content_id.strip() or not self.creator_id.strip():
            raise ValueError("platform, content_id and creator_id are required")
        if not self.evidence_ref.strip():
            raise ValueError("evidence_ref is required")
        if self.views < 0 or self.creator_baseline_views < 0:
            raise ValueError("view counts cannot be negative")
        published = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        if published.tzinfo is None or observed.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        if observed < published:
            raise ValueError("observed_at cannot precede published_at")

    @property
    def age_hours(self) -> float:
        self.validate()
        published = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        age_seconds = (observed - published).total_seconds()
        if age_seconds < 60.0:
            raise ValueError("content age is too short for reliable rate")
        return age_seconds / 3600.0

    @property
    def views_per_hour(self) -> float:
        return self.views / self.age_hours

    @property
    def relative_performance(self) -> float:
        if self.creator_baseline_views <= 0:
            raise ValueError("creator baseline is unknown")
        return self.views / self.creator_baseline_views


@dataclass(frozen=True)
class OutlierSignal:
    content_id: str
    platform: str
    relative_performance: float
    views_per_hour: float
    velocity_ratio: float
    outlier_strength: float
    evidence_ref: str
    formula_version: str = "outlier.v1"


def _robust_ratio(value: float, peers: list[float]) -> float:
    positive = [x for x in peers if x >= 0]
    if not positive:
        raise ValueError("peer baseline requires at least one valid peer")
    baseline = median(positive)
    if baseline <= 1e-6:
        return 1.0 if value > 0 else 0.0
    return value / baseline


def detect_outlier(
    observation: ContentObservation,
    peer_observations: list[ContentObservation],
) -> OutlierSignal:
    observation.validate()
    peers = [
        p for p in peer_observations
        if p.platform == observation.platform and p.content_id != observation.content_id
    ]
    for peer in peers:
        peer.validate()

    velocity_ratio = _robust_ratio(
        observation.views_per_hour,
        [p.views_per_hour for p in peers],
    )
    relative = observation.relative_performance

    # Compress extreme ratios so a single huge number cannot dominate indefinitely.
    # v1 is intentionally simple and versioned; weights require later empirical calibration.
    raw = 0.55 * log1p(relative) + 0.45 * log1p(velocity_ratio)
    strength = 1.0 - (1.0 / (1.0 + raw)) if raw > 0 else 0.0

    return OutlierSignal(
        content_id=observation.content_id,
        platform=observation.platform,
        relative_performance=round(relative, 6),
        views_per_hour=round(observation.views_per_hour, 6),
        velocity_ratio=round(velocity_ratio, 6),
        outlier_strength=round(strength, 6),
        evidence_ref=observation.evidence_ref,
    )
