from __future__ import annotations

from dataclasses import dataclass
from .models import CreativePlan, Decision, GateResult


@dataclass(frozen=True)
class Policy:
    max_cost: float = 25.0
    allowed_platforms: tuple[str, ...] = ("youtube", "instagram", "tiktok")


def verify(plan: CreativePlan, policy: Policy = Policy()) -> GateResult:
    reasons: list[str] = []
    if not plan.original:
        reasons.append("CONTENT_NOT_ORIGINAL")
    if not plan.rights_confirmed:
        reasons.append("RIGHTS_NOT_CONFIRMED")
    if plan.platform not in policy.allowed_platforms:
        reasons.append("PLATFORM_NOT_ALLOWED")
    if plan.estimated_cost < 0 or plan.estimated_cost > policy.max_cost:
        reasons.append("BUDGET_POLICY_FAILED")
    if reasons:
        return GateResult(Decision.BLOCK, tuple(reasons))
    return GateResult(Decision.ACCEPT, ("POLICY_PASS",))
