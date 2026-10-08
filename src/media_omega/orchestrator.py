from __future__ import annotations

from dataclasses import asdict
import json

from .evidence import record_evidence, resolve_evidence
from .intelligence_pipeline import IntelligenceSignal, rank_signals
from .memory import DecisionJournal
from .models import AssetManifest, CreativePlan, Decision, GateResult
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

    def _require_reported_signal(self, signal: IntelligenceSignal) -> None:
        expected = json.loads(json.dumps(
            asdict(signal),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ))
        for event in reversed(self.journal.read_all()):
            if event["event_type"] != "INTELLIGENCE_REPORT":
                continue
            ready = event["payload"].get("ready")
            if isinstance(ready, list) and expected in ready:
                return
        raise ValueError("intelligence signal was not produced by a journaled report")

    def choose_intelligence(self, signals: list[IntelligenceSignal]) -> IntelligenceSignal:
        if not signals:
            raise ValueError("no intelligence signals supplied")
        if any(signal.status != "READY" for signal in signals):
            raise ValueError("only READY intelligence signals may be selected")
        ranked = rank_signals(signals)
        winner = ranked[0]
        if not winner.source_evidence_refs:
            raise ValueError("selected intelligence signal lacks source provenance")
        self._require_reported_signal(winner)

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

    def plan_selected(self, plan: CreativePlan) -> GateResult:
        entity_id = plan.opportunity_id.strip()
        if not entity_id:
            raise ValueError("plan opportunity_id is required")

        current = self.states.current_state(entity_id)
        if current is WorkflowState.PLANNED:
            latest = self.states.history(entity_id)[-1]
            if latest.evidence.plan_id != plan.id:
                raise ValueError("opportunity already has a different plan")
            record = resolve_evidence(self.journal, latest.evidence.plan_ref)
            expected = asdict(plan)
            expected["entity_id"] = entity_id
            expected["plan_id"] = plan.id
            expected["policy_decision"] = Decision.ACCEPT.value
            if record is None or record.payload != expected:
                raise ValueError("plan replay differs from admitted plan")
            return GateResult(Decision.ACCEPT, ("PLAN_ALREADY_ADMITTED",))
        if current is not WorkflowState.EVIDENCE_COLLECTED:
            raise ValueError("opportunity must be selected before planning")

        gate = verify(plan, self.policy)
        self.journal.append("PLAN_POLICY_DECISION", {
            "entity_id": entity_id,
            "plan_id": plan.id,
            "decision": gate.decision.value,
            "reasons": list(gate.reasons),
        })

        if gate.decision is not Decision.ACCEPT:
            # A plan-level failure must not permanently kill the opportunity.
            # The system may submit a corrected/original plan later.
            return gate

        payload = asdict(plan)
        payload["entity_id"] = entity_id
        payload["plan_id"] = plan.id
        payload["policy_decision"] = gate.decision.value
        receipt = record_evidence(
            self.journal,
            "creative_plan.v1",
            payload,
        )
        self.states.transition(
            entity_id,
            WorkflowState.PLANNED,
            TransitionEvidence(
                plan_id=plan.id,
                plan_ref=receipt.evidence_ref,
            ),
        )
        return gate

    def create_assets(self, plan: CreativePlan, creator: object) -> AssetManifest:
        entity_id = plan.opportunity_id.strip()
        if not entity_id:
            raise ValueError("plan opportunity_id is required")

        current = self.states.current_state(entity_id)
        if current is WorkflowState.ASSETS_READY:
            latest = self.states.history(entity_id)[-1]
            if latest.evidence.plan_id != plan.id:
                raise ValueError("assets belong to a different plan")
            if len(latest.evidence.asset_manifest_refs) != 1:
                raise RuntimeError("canonical creator path requires one asset manifest")
            record = resolve_evidence(
                self.journal,
                latest.evidence.asset_manifest_refs[0],
            )
            if record is None:
                raise RuntimeError("asset manifest evidence is missing")
            return AssetManifest(
                entity_id=entity_id,
                plan_id=plan.id,
                assets=tuple(record.payload["assets"]),
                provider=str(record.payload["provider"]),
            )

        if current is not WorkflowState.PLANNED:
            raise ValueError("opportunity must be PLANNED before asset creation")

        planned = self.states.history(entity_id)[-1]
        if planned.evidence.plan_id != plan.id:
            raise ValueError("creator plan does not match admitted plan")
        admitted = resolve_evidence(self.journal, planned.evidence.plan_ref)
        expected = asdict(plan)
        expected["entity_id"] = entity_id
        expected["plan_id"] = plan.id
        expected["policy_decision"] = Decision.ACCEPT.value
        if admitted is None or admitted.payload != expected:
            raise ValueError("creator plan differs from admitted plan")

        provider = getattr(creator, "name", "")
        create = getattr(creator, "create", None)
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("creator provider name is required")
        if not callable(create):
            raise ValueError("creator must provide create(plan, idempotency_key=...)")

        raw_assets = create(plan, idempotency_key=plan.id)
        if not isinstance(raw_assets, (list, tuple)) or not raw_assets:
            raise ValueError("creator must return at least one asset")
        assets = tuple(raw_assets)
        if any(not isinstance(asset, str) or not asset.strip() for asset in assets):
            raise ValueError("creator assets must be non-empty strings")
        if len(set(assets)) != len(assets):
            raise ValueError("creator assets must be unique")

        manifest = AssetManifest(
            entity_id=entity_id,
            plan_id=plan.id,
            assets=assets,
            provider=provider.strip(),
        )
        receipt = record_evidence(
            self.journal,
            manifest.version,
            manifest,
        )
        self.states.transition(
            entity_id,
            WorkflowState.ASSETS_READY,
            TransitionEvidence(
                plan_id=plan.id,
                asset_manifest_refs=(receipt.evidence_ref,),
            ),
        )
        return manifest

