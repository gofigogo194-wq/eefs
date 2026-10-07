from __future__ import annotations

from dataclasses import dataclass
from math import log1p

from .baseline import relative_to_creator
from .baseline_cache import CreatorBaselineCache
from .observations import ContentObservation
from .timeseries import momentum


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
    version: str = "intelligence_pipeline.v2"


def evaluate_content(
    history: list[ContentObservation],
    baseline_cache: CreatorBaselineCache,
) -> IntelligenceSignal:
    if len(history) < 3:
        raise ValueError("intelligence pipeline requires at least 3 snapshots")
    ordered = sorted(history, key=lambda x: x.observed_at)
    latest = ordered[-1]
    baseline_result = baseline_cache.get(latest.creator_id, latest.content_id)
    if baseline_result.baseline is None:
        return IntelligenceSignal(
            latest.content_id, latest.creator_id, 0.0, 0.0, 0.0, 0.0,
            min(len(history) / 6.0, 1.0), 0.0, "INSUFFICIENT_CREATOR_HISTORY"
        )

    trend = momentum(ordered)
    relative = relative_to_creator(latest.views, baseline_result.baseline)
    history_conf = min(len(history) / 6.0, 1.0)
    evidence = round(0.5 * history_conf + 0.5 * baseline_result.baseline.confidence, 6)

    # Compress nothing here yet: keep v1 transparent and auditable.
    raw_strength = 0.5 * max(relative, 0.0) + 0.5 * max(trend.acceleration_ratio, 0.0)
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
