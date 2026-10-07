from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite, log1p

from .baseline import relative_to_creator
from .baseline_cache import CreatorBaselineCache
from .cohort import PeerCohortPolicy, build_peer_cohort
from .observations import ContentObservation
from .timeseries import momentum


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class IntelligencePolicy:
    max_baseline_skew_seconds: float = 900.0

    def validate(self) -> None:
        if (
            not isfinite(self.max_baseline_skew_seconds)
            or self.max_baseline_skew_seconds <= 0
        ):
            raise ValueError("max_baseline_skew_seconds must be finite and positive")


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
    peer_cohort_status: str = "NOT_EVALUATED"
    peer_count: int = 0
    peer_cohort_version: str = "peer_cohort.v1"
    version: str = "intelligence_pipeline.v4"
    platform: str = "youtube"
    source_evidence_refs: tuple[str, ...] = ()
    baseline_max_skew_seconds: float = 0.0


def evaluate_content(
    history: list[ContentObservation],
    baseline_cache: CreatorBaselineCache,
    peer_observations: list[ContentObservation] | None = None,
    cohort_policy: PeerCohortPolicy | None = None,
    policy: IntelligencePolicy | None = None,
) -> IntelligenceSignal:
    if len(history) < 3:
        raise ValueError("intelligence pipeline requires at least 3 snapshots")
    policy = policy or IntelligencePolicy()
    policy.validate()

    ordered = sorted(history, key=lambda x: _time(x.observed_at))
    latest = ordered[-1]
    trend = momentum(ordered)

    cohort_status = "NOT_EVALUATED"
    peer_count = 0
    if cohort_policy is not None:
        cohort = build_peer_cohort(
            latest,
            peer_observations or [],
            cohort_policy,
        )
        cohort_status = cohort.status
        peer_count = len(cohort.peer_content_ids)

    baseline_result = baseline_cache.get(
        latest.creator_id,
        latest.content_id,
    )
    source_evidence_refs = tuple(dict.fromkeys(
        [item.evidence_ref for item in ordered]
        + list(baseline_result.source_refs)
    ))

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
            cohort_status,
            peer_count,
            platform=latest.platform,
            source_evidence_refs=source_evidence_refs,
        )

    if not baseline_result.source_observed_at:
        return IntelligenceSignal(
            latest.content_id,
            latest.creator_id,
            0.0,
            trend.acceleration_ratio,
            trend.latest_velocity,
            baseline_result.baseline.confidence,
            0.0,
            0.0,
            "UNRELIABLE_CREATOR_BASELINE_TIME",
            cohort_status,
            peer_count,
            platform=latest.platform,
            source_evidence_refs=source_evidence_refs,
        )

    latest_time = _time(latest.observed_at)
    max_skew = max(
        abs((_time(value) - latest_time).total_seconds())
        for value in baseline_result.source_observed_at
    )
    if max_skew > policy.max_baseline_skew_seconds:
        return IntelligenceSignal(
            latest.content_id,
            latest.creator_id,
            0.0,
            trend.acceleration_ratio,
            trend.latest_velocity,
            baseline_result.baseline.confidence,
            0.0,
            0.0,
            "STALE_CREATOR_BASELINE",
            cohort_status,
            peer_count,
            platform=latest.platform,
            source_evidence_refs=source_evidence_refs,
            baseline_max_skew_seconds=round(max_skew, 6),
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
        cohort_status,
        peer_count,
        platform=latest.platform,
        source_evidence_refs=source_evidence_refs,
        baseline_max_skew_seconds=round(max_skew, 6),
    )


def rank_signals(signals: list[IntelligenceSignal]) -> list[IntelligenceSignal]:
    return sorted(
        signals,
        key=lambda x: (-x.score, -x.evidence_sufficiency, x.content_id),
    )
