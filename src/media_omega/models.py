from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Decision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class Opportunity:
    source: str
    topic: str
    outlier_strength: float
    demand_growth: float
    competition_inverse: float
    expected_retention: float
    monetization: float
    production_cost: float
    risk: float
    evidence_refs: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class ScoredOpportunity:
    opportunity: Opportunity
    score: float
    formula_version: str


@dataclass(frozen=True)
class CreativePlan:
    opportunity_id: str
    platform: str
    format: str
    title: str
    original: bool = True
    rights_confirmed: bool = True
    estimated_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class GateResult:
    decision: Decision
    reasons: tuple[str, ...]


def to_dict(value: Any) -> dict[str, Any]:
    result = asdict(value)
    if isinstance(result.get("decision"), Enum):
        result["decision"] = result["decision"].value
    return result
