from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from threading import RLock

from .evidence import evidence_ref_exists
from .memory import DecisionJournal


class WorkflowState(str, Enum):
    IDEA = "IDEA"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    PLANNED = "PLANNED"
    ASSETS_READY = "ASSETS_READY"
    VERIFIED = "VERIFIED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    MEASURED = "MEASURED"
    LEARNED = "LEARNED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


_ALLOWED: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.IDEA: frozenset({
        WorkflowState.EVIDENCE_COLLECTED,
        WorkflowState.REJECTED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.EVIDENCE_COLLECTED: frozenset({
        WorkflowState.PLANNED,
        WorkflowState.REJECTED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.PLANNED: frozenset({
        WorkflowState.ASSETS_READY,
        WorkflowState.REJECTED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.ASSETS_READY: frozenset({
        WorkflowState.VERIFIED,
        WorkflowState.REJECTED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.VERIFIED: frozenset({
        WorkflowState.SCHEDULED,
        WorkflowState.REJECTED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.SCHEDULED: frozenset({
        WorkflowState.PUBLISHED,
        WorkflowState.REJECTED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.PUBLISHED: frozenset({
        WorkflowState.MEASURED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.MEASURED: frozenset({
        WorkflowState.LEARNED,
        WorkflowState.BLOCKED,
    }),
    WorkflowState.LEARNED: frozenset(),
    WorkflowState.REJECTED: frozenset(),
    WorkflowState.BLOCKED: frozenset(),
}


@dataclass(frozen=True)
class TransitionEvidence:
    evidence_refs: tuple[str, ...] = ()
    plan_id: str = ""
    asset_refs: tuple[str, ...] = ()
    verification_ref: str = ""
    policy_decision: str = ""
    schedule_id: str = ""
    publication_receipt_ref: str = ""
    published: bool = False
    metric_refs: tuple[str, ...] = ()
    learning_version: str = ""
    learning_evidence_ref: str = ""


@dataclass(frozen=True)
class StateTransition:
    entity_id: str
    from_state: WorkflowState | None
    to_state: WorkflowState
    reason: str
    evidence: TransitionEvidence
    contract_version: str = "state_transition.v1"


class StateTransitionEngine:
    def __init__(self, journal: DecisionJournal) -> None:
        self.journal = journal
        self._lock = RLock()

    def _events_for(self, entity_id: str) -> list[dict]:
        if not entity_id.strip():
            raise ValueError("entity_id is required")
        return [
            event
            for event in self.journal.read_all()
            if event["event_type"] == "STATE_TRANSITION"
            and event["payload"].get("entity_id") == entity_id
        ]

    def history(self, entity_id: str) -> tuple[StateTransition, ...]:
        events = self._events_for(entity_id)
        result: list[StateTransition] = []
        expected_from: WorkflowState | None = None
        for index, event in enumerate(events):
            payload = event["payload"]
            raw_from = payload.get("from_state")
            raw_to = payload.get("to_state")
            try:
                from_state = WorkflowState(raw_from) if raw_from is not None else None
                to_state = WorkflowState(raw_to)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("invalid state transition event") from exc
            if index == 0:
                if from_state is not None or to_state is not WorkflowState.IDEA:
                    raise RuntimeError("state history must begin at IDEA")
            elif from_state is not expected_from:
                raise RuntimeError("state transition history is inconsistent")
            evidence_raw = payload.get("evidence") or {}
            try:
                evidence = TransitionEvidence(
                    evidence_refs=tuple(evidence_raw.get("evidence_refs", ())),
                    plan_id=str(evidence_raw.get("plan_id", "")),
                    asset_refs=tuple(evidence_raw.get("asset_refs", ())),
                    verification_ref=str(evidence_raw.get("verification_ref", "")),
                    policy_decision=str(evidence_raw.get("policy_decision", "")),
                    schedule_id=str(evidence_raw.get("schedule_id", "")),
                    publication_receipt_ref=str(
                        evidence_raw.get("publication_receipt_ref", "")
                    ),
                    published=bool(evidence_raw.get("published", False)),
                    metric_refs=tuple(evidence_raw.get("metric_refs", ())),
                    learning_version=str(evidence_raw.get("learning_version", "")),
                    learning_evidence_ref=str(
                        evidence_raw.get("learning_evidence_ref", "")
                    ),
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError("invalid state transition evidence") from exc
            result.append(StateTransition(
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                reason=str(payload.get("reason", "")),
                evidence=evidence,
                contract_version=str(
                    payload.get("contract_version", "state_transition.v1")
                ),
            ))
            expected_from = to_state
        return tuple(result)

    def current_state(self, entity_id: str) -> WorkflowState | None:
        history = self.history(entity_id)
        return history[-1].to_state if history else None

    def register(self, entity_id: str) -> StateTransition:
        with self._lock:
            if self.current_state(entity_id) is not None:
                raise ValueError("entity is already registered")
            transition = StateTransition(
                entity_id=entity_id,
                from_state=None,
                to_state=WorkflowState.IDEA,
                reason="",
                evidence=TransitionEvidence(),
            )
            self.journal.append("STATE_TRANSITION", {
                "entity_id": transition.entity_id,
                "from_state": None,
                "to_state": transition.to_state.value,
                "reason": transition.reason,
                "evidence": asdict(transition.evidence),
                "contract_version": transition.contract_version,
            })
            return transition

    def transition(
        self,
        entity_id: str,
        to_state: WorkflowState,
        evidence: TransitionEvidence | None = None,
        reason: str = "",
    ) -> StateTransition:
        evidence = evidence or TransitionEvidence()
        with self._lock:
            current = self.current_state(entity_id)
            if current is None:
                raise ValueError("entity is not registered")
            if to_state not in _ALLOWED[current]:
                raise ValueError(
                    f"invalid state transition: {current.value} -> {to_state.value}"
                )
            self._validate_contract(to_state, evidence, reason)
            transition = StateTransition(
                entity_id=entity_id,
                from_state=current,
                to_state=to_state,
                reason=reason.strip(),
                evidence=evidence,
            )
            self.journal.append("STATE_TRANSITION", {
                "entity_id": transition.entity_id,
                "from_state": current.value,
                "to_state": to_state.value,
                "reason": transition.reason,
                "evidence": asdict(evidence),
                "contract_version": transition.contract_version,
            })
            return transition

    def _require_journal_refs(self, refs: tuple[str, ...], label: str) -> None:
        if not refs:
            raise ValueError(f"{label} evidence is required")
        for ref in refs:
            if not evidence_ref_exists(self.journal, ref):
                raise ValueError(f"{label} evidence is not journal-verified")

    def _validate_contract(
        self,
        to_state: WorkflowState,
        evidence: TransitionEvidence,
        reason: str,
    ) -> None:
        if to_state is WorkflowState.EVIDENCE_COLLECTED:
            self._require_journal_refs(evidence.evidence_refs, "collected")
        elif to_state is WorkflowState.PLANNED:
            if not evidence.plan_id.strip():
                raise ValueError("plan_id is required")
        elif to_state is WorkflowState.ASSETS_READY:
            if not evidence.asset_refs or any(not ref.strip() for ref in evidence.asset_refs):
                raise ValueError("asset_refs are required")
        elif to_state is WorkflowState.VERIFIED:
            self._require_journal_refs(
                (evidence.verification_ref,) if evidence.verification_ref else (),
                "verification",
            )
            if evidence.policy_decision != "ACCEPT":
                raise ValueError("verified state requires policy ACCEPT")
        elif to_state is WorkflowState.SCHEDULED:
            if not evidence.schedule_id.strip():
                raise ValueError("schedule_id is required")
        elif to_state is WorkflowState.PUBLISHED:
            self._require_journal_refs(
                (
                    evidence.publication_receipt_ref,
                ) if evidence.publication_receipt_ref else (),
                "publication receipt",
            )
            if evidence.published is not True:
                raise ValueError("published state requires confirmed publication")
        elif to_state is WorkflowState.MEASURED:
            self._require_journal_refs(evidence.metric_refs, "measurement")
        elif to_state is WorkflowState.LEARNED:
            if not evidence.learning_version.strip():
                raise ValueError("learning_version is required")
            self._require_journal_refs(
                (
                    evidence.learning_evidence_ref,
                ) if evidence.learning_evidence_ref else (),
                "learning",
            )
        elif to_state in (WorkflowState.REJECTED, WorkflowState.BLOCKED):
            if not reason.strip():
                raise ValueError("terminal rejection/block reason is required")
