# MEDIA Ω

Autonomous, evidence-driven media operator under construction.

## Mission

Build a platform-neutral media agent that can discover content opportunities, choose a format and platform, create original content, publish through approved APIs, measure outcomes, and improve future decisions from evidence.

The first proving ground is RELAX SABAI MUSIK, but the architecture is not tied to relaxation content, long-form video, Shorts, or any single platform.

## Operating loop

DISCOVER → OBSERVE → COMPARE → SELECT → PLAN + VERIFY → PUBLISH → MEASURE + LEARN

The system deliberately keeps one live path for each responsibility. Reliability should come from explicit contracts, restart-safe persistence, and tests — not from adding duplicate agents, scores, or pipelines. See `docs/SIMPLE_FLOW.md`.

## Non-negotiable invariants

- No credential or secret is committed to the repository.
- No public publishing until the publishing path has passed dry-run and sandbox/private tests.
- Original/authorized media only; trend discovery is not permission to copy content.
- Every autonomous decision must leave an auditable decision record.
- Metrics are observations, not proof of causality.
- Learning changes strategy only through versioned candidates and measurable evidence.
- Platform policy, copyright, account safety, and budget limits override growth objectives.
- A failed or uncertain safety/policy check fails closed.
- Production credentials and destructive account actions require an explicit capability grant.
- No workflow state may be skipped merely because a caller claims success.
- A PUBLISHED state requires journal-verified publication evidence whose payload confirms a real publication.

## Candidate status

The Candidate currently proves the read-only path:

YouTube discovery → persisted observations → temporal momentum → age-normalized creator baseline v2 → peer-cohort diagnostics → IntelligenceSignal v4 → Orchestrator selection → one policy-checked CreativePlan → one creator adapter → typed asset manifest → ASSETS_READY state.

The former duplicate intelligence/scoring, scout, baseline-collection, momentum-report, generic-source, and stale YouTube wrapper paths have been retired. Workflow transitions are enforced by a centralized state engine. The decision journal uses SQLite append-only guards plus a tamper-evident hash chain. Evidence references are content-addressed and bind both evidence type and payload.

Candidate CI currently gates Python 3.11–3.14 on Linux and Python 3.14 on Windows with pinned pytest.

Planning and creation are intentionally linear: one selected opportunity admits one exact plan, and one creator adapter may produce one manifest for that plan using the plan id as the idempotency key. A failed plan check does not permanently kill the opportunity. The creator contract is tested with a fake provider; no production creator or publisher exists yet. No autonomous public-publishing claim is made.

## Open-source reconnaissance

Initial candidates being evaluated:

- Nuraveda AI Social Agent (MIT): useful reference for scout → script → video → publisher flow and guardrails.
- Postiz (AGPL-3.0): mature publishing/scheduling/analytics reference, but its copyleft license means we should prefer API/integration boundaries rather than casually copying its source into this repository.
- Additional creator/trend/outlier components will be audited before adoption.

See `docs/ARCHITECTURE.md` and `docs/OPEN_SOURCE_AUDIT.md`.
