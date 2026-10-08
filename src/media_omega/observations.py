from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class ContentObservation:
    platform: str
    content_id: str
    creator_id: str
    published_at: str
    observed_at: str
    views: int
    # Legacy storage field retained so existing snapshot DB payloads remain
    # readable. Canonical Intelligence v4 never uses this lifetime-view value.
    creator_baseline_views: float
    evidence_ref: str
    discovery_query: str = ""
    content_format: str = "unknown"

    def validate(self) -> None:
        for value, name in (
            (self.platform, "platform"),
            (self.content_id, "content_id"),
            (self.creator_id, "creator_id"),
            (self.evidence_ref, "evidence_ref"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if isinstance(self.views, bool) or not isinstance(self.views, int) or self.views < 0:
            raise ValueError("views must be a non-negative integer")
        if (
            isinstance(self.creator_baseline_views, bool)
            or not isinstance(self.creator_baseline_views, (int, float))
            or not isfinite(float(self.creator_baseline_views))
            or self.creator_baseline_views < 0
        ):
            raise ValueError("creator_baseline_views must be finite and non-negative")
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
