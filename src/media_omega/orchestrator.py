from __future__ import annotations

from dataclasses import asdict
import json

from .asset_verification import capture_created_asset, verify_asset_manifest
from .evidence import record_evidence, resolve_evidence
from .intelligence_pipeline import IntelligenceSignal, rank_signals
from .memory import DecisionJournal
from .models import (
    AssetManifest,
    AssetRecord,
    CreatedAsset,
    CreativePlan,
    Decision,
    GateResult,
)
from .publication_preparation import prepare_publication, dry_run_receipt
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

    @staticmethod
    def _expected_plan_payload(
        plan: CreativePlan,
        entity_id: str,
    ) -> dict:
        expected = asdict(plan)
        expected["entity_id"] = entity_id
        expected["plan_id"] = plan.id
        expected["policy_decision"] = Decision.ACCEPT.value
        return expected

    def _require_admitted_plan(self, plan: CreativePlan) -> None:
        entity_id = plan.opportunity_id.strip()
        history = self.states.history(entity_id)
        planned = next(
            (
                transition
                for transition in reversed(history)
                if transition.to_state is WorkflowState.PLANNED
            ),
            None,
        )
        if planned is None or planned.evidence.plan_id != plan.id:
            raise ValueError("plan does not match admitted workflow plan")
        admitted = resolve_evidence(self.journal, planned.evidence.plan_ref)
        if (
            admitted is None
            or admitted.payload
            != self._expected_plan_payload(plan, entity_id)
        ):
            raise ValueError("plan differs from admitted plan")

    @staticmethod
    def _manifest_from_record(
        record,
        entity_id: str,
        plan_id: str,
    ) -> AssetManifest:
        if record.receipt.evidence_type != "asset_manifest.v2":
            raise RuntimeError(
                "legacy asset manifest is not eligible for verification"
            )
        payload = record.payload
        if payload.get("version") != "asset_manifest.v2":
            raise RuntimeError("asset manifest version is invalid")
        if payload.get("entity_id") != entity_id:
            raise RuntimeError("asset manifest entity is invalid")
        if payload.get("plan_id") != plan_id:
            raise RuntimeError("asset manifest plan is invalid")

        provider = payload.get("provider")
        raw_assets = payload.get("assets")
        if not isinstance(provider, str) or not provider.strip():
            raise RuntimeError("asset manifest provider is invalid")
        if not isinstance(raw_assets, list) or not raw_assets:
            raise RuntimeError("asset manifest assets are invalid")

        assets: list[AssetRecord] = []
        for raw in raw_assets:
            if not isinstance(raw, dict):
                raise RuntimeError("asset manifest record is invalid")
            try:
                assets.append(AssetRecord(
                    asset_id=raw["asset_id"],
                    path=raw["path"],
                    media_type=raw["media_type"],
                    sha256=raw["sha256"],
                    size_bytes=raw["size_bytes"],
                    provenance=raw["provenance"],
                ))
            except KeyError as exc:
                raise RuntimeError(
                    "asset manifest record is incomplete"
                ) from exc

        return AssetManifest(
            entity_id=entity_id,
            plan_id=plan_id,
            assets=tuple(assets),
            provider=provider,
        )

    def create_assets(
        self,
        plan: CreativePlan,
        creator: object,
    ) -> AssetManifest:
        entity_id = plan.opportunity_id.strip()
        if not entity_id:
            raise ValueError("plan opportunity_id is required")

        current = self.states.current_state(entity_id)
        if current in (WorkflowState.ASSETS_READY, WorkflowState.VERIFIED):
            self._require_admitted_plan(plan)
            latest = self.states.history(entity_id)[-1]
            if latest.evidence.plan_id != plan.id:
                raise ValueError("assets belong to a different plan")
            if len(latest.evidence.asset_manifest_refs) != 1:
                raise RuntimeError(
                    "canonical creator path requires one asset manifest"
                )
            record = resolve_evidence(
                self.journal,
                latest.evidence.asset_manifest_refs[0],
            )
            if record is None:
                raise RuntimeError("asset manifest evidence is missing")
            return self._manifest_from_record(record, entity_id, plan.id)

        if current is not WorkflowState.PLANNED:
            raise ValueError(
                "opportunity must be PLANNED before asset creation"
            )

        self._require_admitted_plan(plan)

        provider = getattr(creator, "name", "")
        create = getattr(creator, "create", None)
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("creator provider name is required")
        if not callable(create):
            raise ValueError(
                "creator must provide create(plan, idempotency_key=...)"
            )

        raw_assets = create(plan, idempotency_key=plan.id)
        if not isinstance(raw_assets, (list, tuple)) or not raw_assets:
            raise ValueError("creator must return at least one asset")
        if any(not isinstance(asset, CreatedAsset) for asset in raw_assets):
            raise ValueError(
                "creator assets must use the CreatedAsset contract"
            )

        assets = tuple(
            capture_created_asset(asset)
            for asset in raw_assets
        )
        asset_ids = [asset.asset_id for asset in assets]
        asset_paths = [asset.path for asset in assets]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("creator asset ids must be unique")
        if len(set(asset_paths)) != len(asset_paths):
            raise ValueError("creator asset paths must be unique")

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

    def verify_assets(self, plan: CreativePlan) -> GateResult:
        entity_id = plan.opportunity_id.strip()
        if not entity_id:
            raise ValueError("plan opportunity_id is required")

        current = self.states.current_state(entity_id)
        self._require_admitted_plan(plan)

        if current is WorkflowState.VERIFIED:
            latest = self.states.history(entity_id)[-1]
            if latest.evidence.plan_id != plan.id:
                raise ValueError("verified assets belong to a different plan")
            if len(latest.evidence.asset_manifest_refs) != 1:
                raise RuntimeError(
                    "verified state requires one asset manifest"
                )
            verification = resolve_evidence(
                self.journal,
                latest.evidence.verification_ref,
            )
            if (
                verification is None
                or verification.receipt.evidence_type != "verification.v1"
                or verification.payload.get("decision") != "ACCEPT"
                or verification.payload.get("plan_id") != plan.id
                or verification.payload.get("asset_manifest_ref")
                != latest.evidence.asset_manifest_refs[0]
            ):
                raise RuntimeError(
                    "verified state has invalid verification evidence"
                )
            return GateResult(
                Decision.ACCEPT,
                ("ASSETS_ALREADY_VERIFIED",),
            )

        if current is not WorkflowState.ASSETS_READY:
            raise ValueError(
                "opportunity must be ASSETS_READY before verification"
            )

        latest = self.states.history(entity_id)[-1]
        if latest.evidence.plan_id != plan.id:
            raise ValueError("asset manifest belongs to a different plan")
        if len(latest.evidence.asset_manifest_refs) != 1:
            raise RuntimeError(
                "canonical verification requires one asset manifest"
            )
        manifest_ref = latest.evidence.asset_manifest_refs[0]
        record = resolve_evidence(self.journal, manifest_ref)
        if record is None:
            raise RuntimeError("asset manifest evidence is missing")
        manifest = self._manifest_from_record(
            record,
            entity_id,
            plan.id,
        )

        gate = verify_asset_manifest(manifest, plan)
        verification_payload = {
            "entity_id": entity_id,
            "plan_id": plan.id,
            "asset_manifest_ref": manifest_ref,
            "decision": gate.decision.value,
            "reasons": list(gate.reasons),
            "checked_asset_ids": [
                asset.asset_id for asset in manifest.assets
            ],
            "verified_properties": [
                "entity_plan_binding",
                "file_existence",
                "non_empty",
                "sha256",
                "size",
                "media_type",
                "provenance",
                "platform_media",
            ],
        }
        receipt = record_evidence(
            self.journal,
            "verification.v1",
            verification_payload,
        )
        if gate.decision is not Decision.ACCEPT:
            return gate

        self.states.transition(
            entity_id,
            WorkflowState.VERIFIED,
            TransitionEvidence(
                plan_id=plan.id,
                asset_manifest_refs=(manifest_ref,),
                verification_ref=receipt.evidence_ref,
                policy_decision=Decision.ACCEPT.value,
            ),
        )
        return gate


    def schedule_dry_run(
        self,
        plan: CreativePlan,
        scheduled_at: str,
        description: str = "",
        visibility: str = "private",
    ) -> dict:
        """Prepare one private YouTube schedule; never invoke a provider."""
        entity_id = plan.opportunity_id.strip()
        self._require_admitted_plan(plan)
        current = self.states.current_state(entity_id)
        if current not in (WorkflowState.VERIFIED, WorkflowState.SCHEDULED):
            raise ValueError("assets must be VERIFIED before scheduling")

        history = self.states.history(entity_id)
        verified = next(
            (event for event in reversed(history)
             if event.to_state is WorkflowState.VERIFIED),
            None,
        )
        if verified is None or len(verified.evidence.asset_manifest_refs) != 1:
            raise RuntimeError("canonical VERIFIED evidence is required")
        manifest_ref = verified.evidence.asset_manifest_refs[0]
        manifest_record = resolve_evidence(self.journal, manifest_ref)
        if manifest_record is None:
            raise RuntimeError("admitted manifest is missing")
        manifest = self._manifest_from_record(manifest_record, entity_id, plan.id)

        # Replay does not trust a historic VERIFIED receipt as proof that
        # files still exist or still contain the original verified bytes.
        gate = verify_asset_manifest(manifest, plan)
        if gate.decision is not Decision.ACCEPT:
            raise ValueError("current asset integrity check failed: " + ",".join(gate.reasons))

        package = prepare_publication(
            plan, manifest_ref, verified.evidence.verification_ref,
            scheduled_at, description, visibility,
        )
        if current is WorkflowState.SCHEDULED:
            latest = history[-1]
            existing = resolve_evidence(self.journal, latest.evidence.schedule_ref)
            if (
                existing is None
                or existing.receipt.evidence_type != "schedule.v2"
                or existing.payload != package.payload()
                or latest.evidence.schedule_id != package.schedule_id
            ):
                raise ValueError("opportunity already scheduled with different package")
            return dry_run_receipt(package)

        receipt = record_evidence(self.journal, package.version, package.payload())
        self.states.transition(
            entity_id,
            WorkflowState.SCHEDULED,
            TransitionEvidence(
                plan_id=plan.id,
                asset_manifest_refs=(manifest_ref,),
                verification_ref=verified.evidence.verification_ref,
                schedule_id=package.schedule_id,
                schedule_ref=receipt.evidence_ref,
            ),
        )
        return dry_run_receipt(package)
