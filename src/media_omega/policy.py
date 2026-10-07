from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .models import CreativePlan, Decision, GateResult


@dataclass(frozen=True)
class Policy:
    max_cost: float = 25.0
    allowed_platforms: tuple[str, ...] = ("youtube", "instagram", "tiktok")

    def validate(self) -> None:
        if not isfinite(self.max_cost) or self.max_cost < 0:
            raise ValueError("max_cost must be finite and non-negative")
        if not self.allowed_platforms:
            raise ValueError("allowed_platforms cannot be empty")
        if any(not value.strip() for value in self.allowed_platforms):
            raise ValueError("allowed platform names cannot be empty")
        if len(set(self.allowed_platforms)) != len(self.allowed_platforms):
            raise ValueError("allowed_platforms cannot contain duplicates")


def verify(plan: CreativePlan, policy: Policy = Policy()) -> GateResult:
    policy.validate()
    reasons: list[str] = []
    if not plan.opportunity_id.strip():
        reasons.append("OPPORTUNITY_ID_REQUIRED")
    if not plan.platform.strip():
        reasons.append("PLATFORM_REQUIRED")
    if not plan.format.strip():
        reasons.append("FORMAT_REQUIRED")
    if not plan.title.strip():
        reasons.append("TITLE_REQUIRED")
    if not plan.original:
        reasons.append("CONTENT_NOT_ORIGINAL")
    if not plan.rights_confirmed:
        reasons.append("RIGHTS_NOT_CONFIRMED")
    if plan.platform not in policy.allowed_platforms:
        reasons.append("PLATFORM_NOT_ALLOWED")
    if not isfinite(plan.estimated_cost) or plan.estimated_cost < 0 or plan.estimated_cost > policy.max_cost:
        reasons.append("BUDGET_POLICY_FAILED")
    if reasons:
        return GateResult(Decision.BLOCK, tuple(reasons))
    return GateResult(Decision.ACCEPT, ("POLICY_PASS",))
