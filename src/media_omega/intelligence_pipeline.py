from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log1p

from .baseline import relative_to_creator
from .baseline_cache import CreatorBaselineCache
from .observations import ContentObservation
from .timeseries import momentum


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class IntelligenceSignal:
    content_id: str
    creator_id: str
    relative_creator_performance: float
    acceleration_ratio: float
    latest_velocity: float
    baseline_confidence: float
    evidence_sufficiency: float
    score: float
    status: str
    version: str = "intelligence_pipeline.v3"


def evaluate_content(
    history: list[ContentObservation],
    baseline_cache: CreatorBaselineCache,
) -> IntelligenceSignal:
    if len(history) < 3:
        raise ValueError("intelligence pipeline requires at least 3 snapshots")
    ordered = sorted(history, key=lambda x: _time(x.observed_at))
    latest = ordered[-1]

    # Validate momentum before any creator-history API work. Bad temporal
    # evidence must fail closed without spending quota or producing a baseline.
    trend = momentum(ordered)
    baseline_result = baseline_cache.get(
        latest.creator_id,
        latest.content_id,
        latest.observed_at,
    )
    if baseline_result.baseline is None:
        return IntelligenceSignal(
            latest.content_id,
            latest.creator_id,
            0.0,
            trend.acceleration_ratio,
            trend.latest_velocity,
            0.0,
            min(len(history) / 6.0, 1.0),
            0.0,
            "INSUFFICIENT_CREATOR_HISTORY",
        )

    relative = relative_to_creator(
        latest.views,
        latest.age_hours,
        baseline_result.baseline,
    )
    history_conf = min(len(history) / 6.0, 1.0)
    evidence = round(
        0.5 * history_conf + 0.5 * baseline_result.baseline.confidence,
        6,
    )

    creator_strength = log1p(max(relative, 0.0))
    momentum_strength = log1p(max(trend.acceleration_ratio, 0.0))
    raw_strength = 0.5 * creator_strength + 0.5 * momentum_strength
    score = round(evidence * raw_strength, 6)
    return IntelligenceSignal(
        latest.content_id,
        latest.creator_id,
        round(relative, 6),
        trend.acceleration_ratio,
        trend.latest_velocity,
        baseline_result.baseline.confidence,
        evidence,
        score,
        "READY",
    )


def rank_signals(signals: list[IntelligenceSignal]) -> list[IntelligenceSignal]:
    return sorted(
        signals,
        key=lambda x: (-x.score, -x.evidence_sufficiency, x.content_id),
    )
