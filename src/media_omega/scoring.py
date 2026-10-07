from __future__ import annotations

from dataclasses import dataclass
from .models import Opportunity, ScoredOpportunity


@dataclass(frozen=True)
class Weights:
    outlier_strength: float = 0.25
    demand_growth: float = 0.20
    competition_inverse: float = 0.15
    expected_retention: float = 0.15
    monetization: float = 0.10
    production_cost: float = 0.05
    risk: float = 0.10


FORMULA_VERSION = "opportunity.v1"


def _unit(value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError("opportunity features must be normalized to [0, 1]")
    return value


def score(opportunity: Opportunity, weights: Weights = Weights()) -> ScoredOpportunity:
    positive = (
        weights.outlier_strength * _unit(opportunity.outlier_strength)
        + weights.demand_growth * _unit(opportunity.demand_growth)
        + weights.competition_inverse * _unit(opportunity.competition_inverse)
        + weights.expected_retention * _unit(opportunity.expected_retention)
        + weights.monetization * _unit(opportunity.monetization)
    )
    penalty = (
        weights.production_cost * _unit(opportunity.production_cost)
        + weights.risk * _unit(opportunity.risk)
    )
    return ScoredOpportunity(opportunity, round(positive - penalty, 6), FORMULA_VERSION)
