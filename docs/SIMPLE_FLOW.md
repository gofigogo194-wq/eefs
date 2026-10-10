# MEDIA Ω — Simple Operating Flow

MEDIA Ω stays intentionally simple. Reliability comes from clear contracts and tests, not from adding more brains, scores, agents, or duplicate pipelines.

## The system is seven steps

1. **DISCOVER** — find public candidate content/opportunities.
2. **OBSERVE** — persist factual snapshots and provenance.
3. **COMPARE** — measure momentum, creator baseline, and peer context.
4. **SELECT** — one canonical Intelligence signal ranks candidates.
5. **PLAN + POLICY CHECK** — create one plan and check required fields, declared rights/originality, platform, and budget.
6. **CREATE + VERIFY + PUBLISH** — create original assets, verify the actual assets, then publish only through an approved idempotent platform adapter.
7. **MEASURE + LEARN** — record outcomes and update versioned strategy from evidence.

## Simplicity rules

- One live path per responsibility. No second scout, scoring brain, state engine, publisher, or learning loop.
- A new module is allowed only when the current canonical flow cannot express a required responsibility cleanly.
- Prefer one explicit status over hidden fallback logic.
- Unknown data stays UNKNOWN; missing data is never invented.
- Replays and restarts must be safe and deterministic.
- Tests prove boundaries; they do not justify adding architectural layers.
- Strategy may become smarter, but the operating flow above does not change without evidence that it must.

## Current read-only operation

The implemented system is intentionally three actions, not a web of agents:

1. **SCOUT** — discover candidates and store the first factual snapshot.
2. **REFRESH** — collect later snapshots. Repeat until there is enough time-series evidence.
3. **INTELLIGENCE** — compare, rank, and select only evidence-ready candidates.

Everything inside those actions is implementation detail. New features must extend this line instead of creating a parallel route.

## Current live boundary

The implemented and tested live path currently ends at:

DISCOVER → OBSERVE → COMPARE → SELECT → PLAN + POLICY CHECK → CREATE → ASSETS_READY → VERIFY → VERIFIED

PLAN + POLICY CHECK is deliberately one step: one selected opportunity gets one exact plan. If the plan declarations, platform, required fields, or budget fail, that plan attempt is rejected and the selected opportunity stays retryable. If they pass, the exact plan is journaled and the workflow reaches PLANNED. This is not yet proof that generated assets are original or licensed; actual asset verification stays after creation.

The creator boundary is now enforced as one path: an admitted plan is passed to one creator adapter with the plan id as the idempotency key. The adapter returns typed local CreatedAsset records. MEDIA Ω independently reads the real files and records one asset_manifest.v2 containing resolved path, media type, SHA256, byte size, provider, and provenance before ASSETS_READY is allowed. The deterministic test creator writes real files; this proves the local contract and recovery behavior, not a production media-generation provider.

VERIFY is one gate, not a second pipeline. It reopens the exact admitted manifest, rereads the files, checks entity/plan binding, existence, non-empty bytes, SHA256, size, media type, provenance, and the minimal platform-media constraint. ACCEPT is journaled as verification.v1 and is bound to the exact ASSETS_READY manifest before VERIFIED is allowed. Missing or changed files fail closed and do not advance state.

VERIFY does not claim independent originality or copyright certainty. Plan-level originality/rights remain declarations, while the verified facts are limited to the concrete properties listed above.

Publishing, measurement, and learning remain future stages. They must extend the same linear flow instead of creating parallel systems.

## Candidate publishing and media readiness

The Candidate contains VERIFIED to SCHEDULED with a journal-bound schedule.v2 and a private YouTube dry-run response. Dry-run always reports published=false, remote_id=null. It performs no provider upload.

Orchestrator.inspect_verified_video(plan) independently rehashes the admitted asset and calls ffprobe to inspect duration, dimensions, codec and optional audio metadata. Missing ffprobe, missing files, invalid probe results, and unsupported codecs block that preflight. VIDEO_PREFLIGHT is recorded in the journal. Metadata inspection does not prove end-to-end decode, media quality, originality, rights or actual platform upload eligibility.

The currently implemented schedule_dry_run does NOT require this optional preflight, and no production uploader exists. Before live upload is ever added, the real publisher must enforce fresh media checks as a mandatory gate; existing dry-run results are not authorization.

## Offline Publisher Adapter candidate

`Orchestrator.publisher_dry_run(plan)` accepts only an already admitted `SCHEDULED` opportunity and reloads its journal-verified `schedule.v2` record. It calls `inspect_verified_video(plan)` afresh: actual file SHA256 verification, ffprobe metadata inspection, and full FFmpeg decoding. Only then is the private offline adapter allowed to emit `PUBLISHER_DRY_RUN` evidence (published=false, remote_id=null). A failed preflight never produces a successful dry-run receipt.

The adapter has no network connection, OAuth integration, or upload capability. A dry-run event is **not** a PUBLISHED state transition. Live YouTube publication, external receipt validation, recovery from an indeterminate remote write, and real account-identity binding remain unimplemented. This Candidate must not be promoted as a live publisher.

## Publisher dry-run crash/replay hardening

The offline publisher receipt now uses `DecisionJournal.append_publisher_dry_run_once`: a SQLite `BEGIN IMMEDIATE` transaction revalidates the event hash-chain, searches all prior `PUBLISHER_DRY_RUN` receipts by `schedule_id`, and atomically inserts only if no matching receipt exists. An identical repeat or restart returns the existing receipt; conflicting content and duplicate historical receipts fail closed. It never marks remote publication or authorizes external side effects. Fresh preflight is still required before each orchestrator call, even when a receipt already exists. Tests cover threads, restart, conflict, invalid claims, and journal corruption. Real provider idempotency and ambiguous remote writes remain unproven and must not be inferred from local SQLite receipt uniqueness.

## Crash boundary and schedule ownership

The atomic offline receipt writer additionally checks for an actual SCHEDULED transition for the same entity and exact schedule_id while holding the SQLite write transaction. Unregistered/orphan receipts are rejected. Fault injection raises between event INSERT and COMMIT to demonstrate rollback and safe retry after reopening the journal. These are local database guarantees only: interruption after an actual remote API write and before saving its acknowledgment remains unsupported and must not be automatically retried.

## Future YouTube upload contract (NO LIVE WRITE)

`youtube_upload_contract.py` introduces a pure deterministic intent bound to schedule, plan, manifest, verification, channel identifier, and SHA256 of the asset. Its channel equality check compares supplied identifiers and is **not OAuth verification**. No uploader, API credentials, authenticated channel readback, remote receipt, or public/private YouTube operation is implemented.

If a future remote request times out after dispatch, the state must be `REMOTE_UNKNOWN`, not a successful upload and not safe to retry. `may_retry_upload` deliberately returns false for all states until the real reconciliation/readback proof and explicit authorization are implemented. This is a safety specification with unit tests, not proof of network idempotency.

## Read-only YouTube reconciliation candidate

`youtube_readback.py` defines an injectable read-only transport for authenticated channel identity and remote-video metadata. It has no real OAuth implementation or HTTP client. Missing permissions, timeouts, absent videos, foreign channels, and public visibility are fail-closed. Even a matching channel/video/private readback remains REMOTE_UNKNOWN because those fields cannot prove that the planned file bytes were uploaded. A future production design needs a durable remote upload attempt identifier plus strong server evidence before any publication transition or retry. No network write or real publishing capability is implemented.

## Actual GET-only YouTube transport (not configured)

`youtube_api_readonly.py` now implements the read-only YouTube Data API `channels.list(mine=true,part=id)` and `videos.list(part=snippet,status,id=...)` mapping. It accepts an already-issued OAuth access token in memory: MEDIA Ω does not perform Google login, refresh, or any upload. It uses only HTTPS GET requests to fixed Google API paths, restricts response size and timeouts, and forbids HTTP redirects to avoid forwarding Bearer tokens. Unit tests simulate responses without requiring credentials. Account access requires a valid OAuth `youtube.readonly` scope. No live, credential-backed readback or target Windows media integration is proven. Remote metadata cannot prove that our specific bytes were uploaded; no remote upload reconciliation can transition to PUBLISHED.

## OAuth PKCE preparation and Windows media CI

`youtube_oauth_readonly.py` generates a local OAuth2 authorization URL scoped ONLY to youtube.readonly, with a random state and PKCE S256 challenge. Only loopback HTTP callbacks are accepted; the code verifier remains in memory. No authorization-code exchange, local callback server, token persistence, refresh, or access to a Google account is implemented. Tests check rejection of unsafe callback addresses and state mismatches. Windows CI now installs FFmpeg and requires the actual MP4 decode integration test rather than silently skipping it. A green simulated OAuth test does not prove Google-approved credentials or real account access.

## OAuth authorization-code exchange Candidate

`youtube_oauth_exchange.py` performs a single-use PKCE authorization-code exchange against Google's fixed token endpoint, validates loopback callback origin and state, disallows HTTP redirects, and rejects missing or unexpectedly broad scopes. The access token remains in process memory and is not journaled. A failed or ambiguous exchange must restart authorization, never automatically reuse the same code. No real Google account authorization, refresh-token storage, long-term secret vault, callback HTTP server, or video upload has been implemented. OAuth exchange unit tests use a fake transport; they do not establish working live credentials.

## One-shot OAuth to channel verification

`ReadOnlyConnectionSession` now joins PKCE authorization preparation, callback validation, one-time code exchange, token-in-memory read-only GET, and expected-channel verification in one canonical path. An unsuccessful step consumes the attempt and requires fresh authorization; tests inject mock transports for success, wrong account, network errors, CSRF, and replay. No local HTTP callback listener, token persistence, real Google login, or upload exists. OAuth end-to-end has only been proven against fake responses; a target-machine real-account test is required before promotion.

## First real ambient MP4 creator

`render_ambient_loop(video, audio, output_mp4, duration_seconds=...)` assembles a local H.264/AAC MP4 from user-provided video and audio by looping both inputs to a specified duration of up to five hours. It writes a temporary `.partial.mp4`, probes codec/audio/duration, fully decodes the output, and only then atomically renames to the requested path; failure deletes the partial output and never overwrites the source or an existing output. This proves valid MP4 assembly only for tested short fixtures; smooth visual/audio loop transitions, production 1–5 hour performance, rights ownership, and integration with the Orchestrator's asset manifest remain future gates. No YouTube upload is possible through this module.

## Audio loop crossfade candidate

`render_ambient_loop(..., audio_crossfade_seconds=0.15)` optionally builds a wrap-around audio unit: source middle followed by equal-power crossfade of source tail and head, then repeats the resulting PCM waveform. This avoids a hard discontinuity at the audio loop reset. The default remains unchanged (`audio_crossfade_seconds=0`), and the overlap accepts up to 1 second. A real FFmpeg short-clip test checks encoded output, duration and audio stream. We have **not** measured audible click thresholds, music perceptual quality, visual loop seamlessness, or multi-hour resource usage. This is an isolated Candidate feature and does not upload videos.

## Visual loop dissolve (Candidate)

`render_ambient_loop(..., video_crossfade_seconds=0.15)` now optionally prepares a rotated video loop at a constant 24 fps by combining its middle segment with an FFmpeg dissolve from tail to head. This is an opt-in technical transition, **not proof of perceptual seamlessness**. Short FFmpeg fixture tests check codec, audio and duration. Slow 1–5h renders, memory, source-specific transitions, visual quality and manual listening/viewing remain unproven. Live publication remains disabled.
