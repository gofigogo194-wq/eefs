from __future__ import annotations

from dataclasses import asdict
from .memory import DecisionJournal
from .models import CreativePlan, Decision, Opportunity
from .policy import Policy, verify
from .scoring import score


class Orchestrator:
    def __init__(self, journal: DecisionJournal, policy: Policy = Policy()) -> None:
        self.journal = journal
        self.policy = policy

    def choose(self, opportunities: list[Opportunity]):
        if not opportunities:
            raise ValueError("no opportunities supplied")
        ranked = sorted((score(x) for x in opportunities), key=lambda x: x.score, reverse=True)
        self.journal.append("RANKED", {
            "formula_version": ranked[0].formula_version,
            "ranking": [{"id": x.opportunity.id, "score": x.score} for x in ranked],
        })
        return ranked[0]

    def dry_run_publish(self, plan: CreativePlan) -> dict[str, object]:
        gate = verify(plan, self.policy)
        self.journal.append("POLICY_DECISION", {
            "plan_id": plan.id, "decision": gate.decision.value, "reasons": list(gate.reasons)
        })
        if gate.decision is not Decision.ACCEPT:
            return {"published": False, "dry_run": True, "reasons": list(gate.reasons)}
        receipt = {"published": False, "dry_run": True, "plan_id": plan.id, "platform": plan.platform}
        self.journal.append("DRY_RUN_PUBLICATION", receipt)
        return receipt
