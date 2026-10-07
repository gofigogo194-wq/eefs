# MEDIA Ω

Autonomous, evidence-driven media operator.

## Mission

Build a platform-neutral media agent that can discover content opportunities, choose a format and platform, create original content, publish through approved APIs, measure outcomes, and improve future decisions from evidence.

The first proving ground is RELAX SABAI MUSIK, but the architecture is not tied to relaxation content, long-form video, Shorts, or any single platform.

## Operating loop

DISCOVER → EVALUATE → PLAN → CREATE → VERIFY → PUBLISH → MEASURE → LEARN

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

## Bootstrap status

**v0.0.1 — architecture/bootstrap**

No production publisher exists yet. No claim of autonomous production operation is made.

## Open-source reconnaissance

Initial candidates being evaluated:

- Nuraveda AI Social Agent (MIT): useful reference for scout → script → video → publisher flow and guardrails.
- Postiz (AGPL-3.0): mature publishing/scheduling/analytics reference, but its copyleft license means we should prefer API/integration boundaries rather than casually copying its source into this repository.
- Additional creator/trend/outlier components will be audited before adoption.

See `docs/ARCHITECTURE.md` and `docs/OPEN_SOURCE_AUDIT.md`.
