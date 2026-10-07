from __future__ import annotations

from .evidence import record_evidence
from .intelligence_pipeline import IntelligenceSignal, rank_signals
from .memory import DecisionJournal
from .models import CreativePlan, Decision
from .policy import Policy, verify
from .state_machine import StateTransitionEngine, TransitionEvidence, WorkflowState


_TERMINAL_STATES = {
    WorkflowState.LEARNED,
    WorkflowState.REJECTED,
    WorkflowState.BLOCKED,
}


class Orchestrator:
    """Control-plane selector.

    Live opportunity selection accepts only canonical IntelligenceSignal values.
    A selected signal is journaled as evidence and admitted to the enforced
    workflow state machine at EVIDENCE_COLLECTED.
    """

    def __init__(self, journal: DecisionJournal, policy: Policy = Policy()) -> None:
        self.journal = journal
        self.policy = policy
        self.states = StateTransitionEngine(journal)

    @staticmethod
    def _entity_id(signal: IntelligenceSignal) -> str:
        if not signal.platform.strip() or not signal.content_id.strip():
            raise ValueError("signal platform and content_id are required")
        return f"{signal.platform}:{signal.content_id}"

    def choose_intelligence(self, signals: list[IntelligenceSignal]) -> IntelligenceSignal:
        if not signals:
            raise ValueError("no intelligence signals supplied")
        if any(signal.status != "READY" for signal in signals):
            raise ValueError("only READY intelligence signals may be selected")
        ranked = rank_signals(signals)
        winner = ranked[0]
        if not winner.source_evidence_refs:
            raise ValueError("selected intelligence signal lacks source provenance")

        entity_id = self._entity_id(winner)
        current = self.states.current_state(entity_id)
        if current in _TERMINAL_STATES:
            raise ValueError("terminal opportunity cannot be re-selected")

        receipt = record_evidence(
            self.journal,
            winner.version,
            winner,
        )
        if current is None:
            self.states.register(entity_id)
            current = WorkflowState.IDEA
        if current is WorkflowState.IDEA:
            self.states.transition(
                entity_id,
                WorkflowState.EVIDENCE_COLLECTED,
                TransitionEvidence(evidence_refs=(receipt.evidence_ref,)),
            )

        self.journal.append("INTELLIGENCE_SELECTION", {
            "formula_version": winner.version,
            "entity_id": entity_id,
            "winner_content_id": winner.content_id,
            "evidence_ref": receipt.evidence_ref,
            "ranking": [
                {
                    "content_id": signal.content_id,
                    "platform": signal.platform,
                    "score": signal.score,
                    "evidence_sufficiency": signal.evidence_sufficiency,
                }
                for signal in ranked
            ],
        })
        return winner

    def dry_run_publish(self, plan: CreativePlan) -> dict[str, object]:
        gate = verify(plan, self.policy)
        self.journal.append("POLICY_DECISION", {
            "plan_id": plan.id,
            "decision": gate.decision.value,
            "reasons": list(gate.reasons),
        })
        if gate.decision is not Decision.ACCEPT:
            return {"published": False, "dry_run": True, "reasons": list(gate.reasons)}
        receipt = {
            "published": False,
            "dry_run": True,
            "plan_id": plan.id,
            "platform": plan.platform,
        }
        self.journal.append("DRY_RUN_PUBLICATION", receipt)
        return receipt
