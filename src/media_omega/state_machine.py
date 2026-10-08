from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from threading import RLock
from typing import Any

from .evidence import EvidenceRecord, resolve_evidence
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
    plan_ref: str = ""
    asset_manifest_refs: tuple[str, ...] = ()
    verification_ref: str = ""
    policy_decision: str = ""
    schedule_id: str = ""
    schedule_ref: str = ""
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


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise RuntimeError(f"{field} must be a list of strings")
    result = tuple(value)
    if any(not isinstance(item, str) for item in result):
        raise RuntimeError(f"{field} must be a list of strings")
    return result


def _string(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"{field} must be a string")
    return value


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

    def _parse_evidence(self, raw: Any) -> TransitionEvidence:
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise RuntimeError("state transition evidence must be an object")
        published = raw.get("published", False)
        if not isinstance(published, bool):
            raise RuntimeError("published must be a boolean")
        return TransitionEvidence(
            evidence_refs=_string_tuple(raw.get("evidence_refs"), "evidence_refs"),
            plan_id=_string(raw.get("plan_id"), "plan_id"),
            plan_ref=_string(raw.get("plan_ref"), "plan_ref"),
            asset_manifest_refs=_string_tuple(
                raw.get("asset_manifest_refs"),
                "asset_manifest_refs",
            ),
            verification_ref=_string(
                raw.get("verification_ref"),
                "verification_ref",
            ),
            policy_decision=_string(
                raw.get("policy_decision"),
                "policy_decision",
            ),
            schedule_id=_string(raw.get("schedule_id"), "schedule_id"),
            schedule_ref=_string(raw.get("schedule_ref"), "schedule_ref"),
            publication_receipt_ref=_string(
                raw.get("publication_receipt_ref"),
                "publication_receipt_ref",
            ),
            published=published,
            metric_refs=_string_tuple(raw.get("metric_refs"), "metric_refs"),
            learning_version=_string(
                raw.get("learning_version"),
                "learning_version",
            ),
            learning_evidence_ref=_string(
                raw.get("learning_evidence_ref"),
                "learning_evidence_ref",
            ),
        )

    def history(self, entity_id: str) -> tuple[StateTransition, ...]:
        events = self._events_for(entity_id)
        result: list[StateTransition] = []
        expected_from: WorkflowState | None = None

        for index, event in enumerate(events):
            payload = event["payload"]
            if payload.get("contract_version") != "state_transition.v1":
                raise RuntimeError("unsupported state transition contract version")

            raw_from = payload.get("from_state")
            raw_to = payload.get("to_state")
            try:
                from_state = WorkflowState(raw_from) if raw_from is not None else None
                to_state = WorkflowState(raw_to)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("invalid state transition event") from exc

            reason = _string(payload.get("reason"), "reason")
            evidence = self._parse_evidence(payload.get("evidence"))

            if index == 0:
                if from_state is not None or to_state is not WorkflowState.IDEA:
                    raise RuntimeError("state history must begin at IDEA")
            else:
                if from_state is not expected_from:
                    raise RuntimeError("state transition history is inconsistent")
                if from_state is None or to_state not in _ALLOWED[from_state]:
                    raise RuntimeError("state transition history contains illegal edge")
                if (
                    to_state is WorkflowState.ASSETS_READY
                    and result
                    and evidence.plan_id != result[-1].evidence.plan_id
                ):
                    raise RuntimeError("asset manifest plan does not match admitted plan")
                try:
                    self._validate_contract(
                        entity_id,
                        to_state,
                        evidence,
                        reason,
                        before_event_id=int(event["id"]),
                    )
                except ValueError as exc:
                    raise RuntimeError(
                        "state transition history violates evidence contract"
                    ) from exc

            transition = StateTransition(
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                evidence=evidence,
            )
            result.append(transition)
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
            payload = {
                "entity_id": transition.entity_id,
                "from_state": None,
                "to_state": transition.to_state.value,
                "reason": transition.reason,
                "evidence": asdict(transition.evidence),
                "contract_version": transition.contract_version,
            }
            self.journal.append_state_transition(
                payload,
                expected_from_state=None,
            )
            return transition

    def transition(
        self,
        entity_id: str,
        to_state: WorkflowState,
        evidence: TransitionEvidence | None = None,
        reason: str = "",
    ) -> StateTransition:
        if not isinstance(to_state, WorkflowState):
            raise ValueError("to_state must be a WorkflowState")
        evidence = evidence or TransitionEvidence()
        with self._lock:
            current = self.current_state(entity_id)
            if current is None:
                raise ValueError("entity is not registered")
            if to_state not in _ALLOWED[current]:
                raise ValueError(
                    f"invalid state transition: {current.value} -> {to_state.value}"
                )
            if to_state is WorkflowState.ASSETS_READY:
                prior = self.history(entity_id)[-1]
                if evidence.plan_id != prior.evidence.plan_id:
                    raise ValueError("asset manifest plan does not match admitted plan")
            self._validate_contract(entity_id, to_state, evidence, reason)
            transition = StateTransition(
                entity_id=entity_id,
                from_state=current,
                to_state=to_state,
                reason=reason.strip(),
                evidence=evidence,
            )
            payload = {
                "entity_id": transition.entity_id,
                "from_state": current.value,
                "to_state": to_state.value,
                "reason": transition.reason,
                "evidence": asdict(evidence),
                "contract_version": transition.contract_version,
            }
            self.journal.append_state_transition(
                payload,
                expected_from_state=current.value,
            )
            return transition

    @staticmethod
    def _record_entity_id(record: EvidenceRecord) -> str:
        explicit = record.payload.get("entity_id")
        if isinstance(explicit, str) and explicit.strip():
            return explicit
        platform = record.payload.get("platform")
        content_id = record.payload.get("content_id")
        if (
            isinstance(platform, str)
            and platform.strip()
            and isinstance(content_id, str)
            and content_id.strip()
        ):
            return f"{platform}:{content_id}"
        return ""

    def _require_records(
        self,
        refs: tuple[str, ...],
        label: str,
        entity_id: str,
        type_prefix: str | None = None,
        before_event_id: int | None = None,
    ) -> tuple[EvidenceRecord, ...]:
        if not refs:
            raise ValueError(f"{label} evidence is required")
        records: list[EvidenceRecord] = []
        for ref in refs:
            record = resolve_evidence(
                self.journal,
                ref,
                before_event_id=before_event_id,
            )
            if record is None:
                raise ValueError(
                    f"{label} evidence was not journal-verified before transition"
                )
            if (
                type_prefix is not None
                and not record.receipt.evidence_type.startswith(type_prefix)
            ):
                raise ValueError(f"{label} evidence has wrong type")
            if self._record_entity_id(record) != entity_id:
                raise ValueError(f"{label} evidence belongs to another entity")
            records.append(record)
        return tuple(records)

    def _validate_contract(
        self,
        entity_id: str,
        to_state: WorkflowState,
        evidence: TransitionEvidence,
        reason: str,
        before_event_id: int | None = None,
    ) -> None:
        if to_state is WorkflowState.EVIDENCE_COLLECTED:
            self._require_records(
                evidence.evidence_refs,
                "collected",
                entity_id,
                before_event_id=before_event_id,
            )

        elif to_state is WorkflowState.PLANNED:
            if not evidence.plan_id.strip():
                raise ValueError("plan_id is required")
            records = self._require_records(
                (evidence.plan_ref,) if evidence.plan_ref else (),
                "plan",
                entity_id,
                "creative_plan.",
                before_event_id,
            )
            if records[0].payload.get("plan_id") != evidence.plan_id:
                raise ValueError("plan evidence does not match plan_id")

        elif to_state is WorkflowState.ASSETS_READY:
            if not evidence.plan_id.strip():
                raise ValueError("asset manifest plan_id is required")
            records = self._require_records(
                evidence.asset_manifest_refs,
                "asset manifest",
                entity_id,
                "asset_manifest.",
                before_event_id,
            )
            for record in records:
                if record.payload.get("plan_id") != evidence.plan_id:
                    raise ValueError("asset manifest does not match plan_id")
                assets = record.payload.get("assets")
                if not isinstance(assets, list) or not assets:
                    raise ValueError("asset manifest must contain assets")

        elif to_state is WorkflowState.VERIFIED:
            records = self._require_records(
                (evidence.verification_ref,) if evidence.verification_ref else (),
                "verification",
                entity_id,
                "verification.",
                before_event_id,
            )
            if evidence.policy_decision != "ACCEPT":
                raise ValueError("verified state requires policy ACCEPT")
            if records[0].payload.get("decision") != "ACCEPT":
                raise ValueError("verification evidence must record ACCEPT")

        elif to_state is WorkflowState.SCHEDULED:
            if not evidence.schedule_id.strip():
                raise ValueError("schedule_id is required")
            records = self._require_records(
                (evidence.schedule_ref,) if evidence.schedule_ref else (),
                "schedule",
                entity_id,
                "schedule.",
                before_event_id,
            )
            if records[0].payload.get("schedule_id") != evidence.schedule_id:
                raise ValueError("schedule evidence does not match schedule_id")

        elif to_state is WorkflowState.PUBLISHED:
            records = self._require_records(
                (
                    evidence.publication_receipt_ref,
                ) if evidence.publication_receipt_ref else (),
                "publication receipt",
                entity_id,
                "publication_receipt.",
                before_event_id,
            )
            if evidence.published is not True:
                raise ValueError("published state requires confirmed publication")
            if records[0].payload.get("published") is not True:
                raise ValueError(
                    "publication evidence does not confirm publication"
                )

        elif to_state is WorkflowState.MEASURED:
            self._require_records(
                evidence.metric_refs,
                "measurement",
                entity_id,
                "measurement.",
                before_event_id,
            )

        elif to_state is WorkflowState.LEARNED:
            if not evidence.learning_version.strip():
                raise ValueError("learning_version is required")
            records = self._require_records(
                (
                    evidence.learning_evidence_ref,
                ) if evidence.learning_evidence_ref else (),
                "learning",
                entity_id,
                "learning.",
                before_event_id,
            )
            if records[0].payload.get("version") != evidence.learning_version:
                raise ValueError(
                    "learning evidence does not match learning_version"
                )

        elif to_state in (WorkflowState.REJECTED, WorkflowState.BLOCKED):
            if not reason.strip():
                raise ValueError("terminal rejection/block reason is required")
