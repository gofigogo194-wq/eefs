from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median

from .evidence import record_evidence
from .memory import DecisionJournal
from .observations import ContentObservation, OutlierSignal, detect_outlier
from .timeseries import MomentumSignal, momentum


@dataclass(frozen=True)
class OpportunityCandidate:
    content_id: str
    platform: str
    outlier_strength: float
    acceleration_ratio: float
    confidence: float
    evidence_count: int
    evidence_refs: tuple[str, ...]
    decision_version: str = "intelligence.v1"


def _confidence(history_count: int, peer_count: int) -> float:
    # Conservative evidence sufficiency only; this is not a probability.
    history_component = min(history_count / 6.0, 1.0)
    peer_component = min(peer_count / 10.0, 1.0)
    return round(0.5 * history_component + 0.5 * peer_component, 6)


def build_candidate(
    history: list[ContentObservation],
    peers: list[ContentObservation],
    journal: DecisionJournal,
) -> OpportunityCandidate:
    if len(history) < 3:
        raise ValueError("candidate requires at least 3 historical observations")

    latest = sorted(history, key=lambda x: x.observed_at)[-1]
    for observation in history:
        record_evidence(journal, "content_observation.v1", observation)
    for peer in peers:
        record_evidence(journal, "peer_observation.v1", peer)

    outlier = detect_outlier(latest, peers)
    trend = momentum(history)
    refs = tuple(dict.fromkeys(
        [x.evidence_ref for x in history] + [x.evidence_ref for x in peers]
    ))

    candidate = OpportunityCandidate(
        content_id=latest.content_id,
        platform=latest.platform,
        outlier_strength=outlier.outlier_strength,
        acceleration_ratio=trend.acceleration_ratio,
        confidence=_confidence(len(history), len(peers)),
        evidence_count=len(history) + len(peers),
        evidence_refs=refs,
    )
    journal.append("OPPORTUNITY_CANDIDATE", asdict(candidate))
    return candidate
