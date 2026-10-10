# MEDIA Ω

Autonomous, evidence-driven media operator under construction.

## Mission

Build a platform-neutral media agent that can discover content opportunities, choose a format and platform, create original content, publish through approved APIs, measure outcomes, and improve future decisions from evidence.

The first proving ground is RELAX SABAI MUSIK, but the architecture is not tied to relaxation content, long-form video, Shorts, or any single platform.

## Operating loop

DISCOVER → OBSERVE → COMPARE → SELECT → PLAN + POLICY CHECK → CREATE → VERIFY → PUBLISH → MEASURE + LEARN

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

YouTube discovery → persisted observations → temporal momentum → age-normalized creator baseline v2 → peer-cohort diagnostics → IntelligenceSignal v4 → Orchestrator selection → one policy-checked CreativePlan → one deterministic creator → real local assets → AssetManifest v2 with SHA256/size/provenance → one Verification Gate → VERIFIED state.

The former duplicate intelligence/scoring, scout, baseline-collection, momentum-report, generic-source, and stale YouTube wrapper paths have been retired. Workflow transitions are enforced by a centralized state engine. The decision journal uses SQLite append-only guards plus a tamper-evident hash chain. Evidence references are content-addressed and bind both evidence type and payload.

Candidate CI currently gates Python 3.11–3.14 on Linux and Python 3.14 on Windows with pinned pytest.

Planning, creation, and verification are intentionally linear: one selected opportunity admits one exact plan, one creator adapter may produce one manifest for that plan using the plan id as the idempotency key, and one verification gate may promote that exact manifest to VERIFIED. A failed plan check does not permanently kill the opportunity. The deterministic creator used by CI writes real files so MEDIA Ω can independently compute and later re-check their SHA256 and byte size. Verification proves file integrity, binding, declared media type, and provenance; it does not claim independent copyright/originality certainty. No production creator or publisher exists yet, and no autonomous public-publishing claim is made.

## Open-source reconnaissance

Initial candidates being evaluated:

- Nuraveda AI Social Agent (MIT): useful reference for scout → script → video → publisher flow and guardrails.
- Postiz (AGPL-3.0): mature publishing/scheduling/analytics reference, but its copyleft license means we should prefer API/integration boundaries rather than casually copying its source into this repository.
- Additional creator/trend/outlier components will be audited before adoption.

See `docs/ARCHITECTURE.md` and `docs/OPEN_SOURCE_AUDIT.md`.

## Windows desktop — find popular YouTube videos

The **Find popular videos** button is read-only. It uses YouTube Data API v3
`videos.list(chart=mostPopular)` with the selected two-letter region and result count (1–50).
This is a regional public popularity chart, **not** a claim that the videos are
safe to re-use, nor a guarantee of early trends, viral prediction or downloads.

To enable it, create a YouTube Data API v3 API key in your own Google Cloud
project with the YouTube Data API v3 enabled. Restrict the key to this API;
never put it in source code, a screenshot, a GitHub issue or a shared archive.
Enter the key in the masked **YouTube API key** field. MEDIA Ω holds this key
only in application memory for the current run; it is not persisted to files.
The standard YouTube API key is transmitted as the documented HTTPS query
parameter to Google's API. Avoid sharing diagnostic URLs containing credentials.

For automated setups the `MEDIA_OMEGA_YOUTUBE_API_KEY` environment variable
is also supported. Existing session OAuth bearer tokens via
`MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN` still work and take precedence. No YouTube
upload, OAuth sign-in, download or public publication is implemented in this desktop.
CI tests mock API responses: **a live account/API-key search on the user's Windows
machine is still a separate acceptance test**.
