from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from .observations import ContentObservation


@dataclass(frozen=True)
class MomentumSignal:
    content_id: str
    sample_count: int
    latest_velocity: float
    previous_velocity: float
    acceleration_ratio: float
    sustained_growth: bool
    formula_version: str = "momentum.v2"


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


def momentum(history: list[ContentObservation], minimum_interval_seconds: float = 60.0) -> MomentumSignal:
    if len(history) < 3:
        raise ValueError("at least 3 observations are required for momentum")
    ordered = sorted(history, key=lambda x: _time(x.observed_at))
    content_ids = {x.content_id for x in ordered}
    platforms = {x.platform for x in ordered}
    if len(content_ids) != 1 or len(platforms) != 1:
        raise ValueError("momentum history must describe one content item on one platform")
    for item in ordered:
        item.validate()

    velocities: list[float] = []
    for left, right in zip(ordered, ordered[1:]):
        dt_hours = (_time(right.observed_at) - _time(left.observed_at)).total_seconds() / 3600.0
        if dt_hours <= 0:
            raise ValueError("observation timestamps must be unique and increasing")
        delta_views = right.views - left.views
        if delta_views < 0:
            raise ValueError("cumulative views cannot decrease")
        velocities.append(delta_views / dt_hours)

    previous = velocities[-2]
    latest = velocities[-1]
    # A zero/near-zero previous interval cannot support a meaningful
    # multiplicative acceleration claim. Keep the transition observable via
    # latest_velocity, but fail closed on the ratio itself.
    if previous <= 1e-6:
        ratio = 1.0 if latest > 0 else 0.0
    else:
        ratio = latest / previous
    sustained = len(velocities) >= 2 and latest > previous and previous > 1e-6

    return MomentumSignal(
        content_id=ordered[-1].content_id,
        sample_count=len(ordered),
        latest_velocity=round(latest, 6),
        previous_velocity=round(previous, 6),
        acceleration_ratio=round(ratio, 6),
        sustained_growth=sustained,
    )
