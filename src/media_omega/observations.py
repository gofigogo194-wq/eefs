from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
