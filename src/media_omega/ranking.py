from __future__ import annotations

from dataclasses import dataclass

from .intelligence import OpportunityCandidate


@dataclass(frozen=True)
class RankedOpportunity:
    rank: int
    content_id: str
    platform: str
    score: float
    outlier_strength: float
    acceleration_ratio: float
    confidence: float
    evidence_count: int


def opportunity_score(candidate: OpportunityCandidate) -> float:
    # Confidence gates the strength signals instead of being interpreted as probability.
    outlier = max(candidate.outlier_strength, 0.0)
    acceleration = max(candidate.acceleration_ratio, 0.0)
    return round(candidate.confidence * (0.6 * outlier + 0.4 * acceleration), 6)


def rank_opportunities(candidates: list[OpportunityCandidate]) -> list[RankedOpportunity]:
    ordered = sorted(
        candidates,
        key=lambda c: (-opportunity_score(c), -c.evidence_count, c.content_id),
    )
    return [
        RankedOpportunity(
            rank=index,
            content_id=c.content_id,
            platform=c.platform,
            score=opportunity_score(c),
            outlier_strength=c.outlier_strength,
            acceleration_ratio=c.acceleration_ratio,
            confidence=c.confidence,
            evidence_count=c.evidence_count,
        )
        for index, c in enumerate(ordered, 1)
    ]
