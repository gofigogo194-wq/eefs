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

    def missing_text(value: object) -> bool:
        return not isinstance(value, str) or not value.strip()

    if missing_text(plan.id):
        reasons.append("PLAN_ID_REQUIRED")
    if missing_text(plan.opportunity_id):
        reasons.append("OPPORTUNITY_ID_REQUIRED")
    if missing_text(plan.platform):
        reasons.append("PLATFORM_REQUIRED")
    if missing_text(plan.format):
        reasons.append("FORMAT_REQUIRED")
    if missing_text(plan.title):
        reasons.append("TITLE_REQUIRED")
    if plan.original is not True:
        reasons.append("CONTENT_NOT_ORIGINAL")
    if plan.rights_confirmed is not True:
        reasons.append("RIGHTS_NOT_CONFIRMED")
    if not isinstance(plan.platform, str) or plan.platform not in policy.allowed_platforms:
        reasons.append("PLATFORM_NOT_ALLOWED")
    if (
        isinstance(plan.estimated_cost, bool)
        or not isinstance(plan.estimated_cost, (int, float))
        or not isfinite(float(plan.estimated_cost))
        or plan.estimated_cost < 0
        or plan.estimated_cost > policy.max_cost
    ):
        reasons.append("BUDGET_POLICY_FAILED")
    if not isinstance(plan.metadata, dict):
        reasons.append("METADATA_MUST_BE_OBJECT")
    if reasons:
        return GateResult(Decision.BLOCK, tuple(reasons))
    return GateResult(Decision.ACCEPT, ("POLICY_PASS",))
