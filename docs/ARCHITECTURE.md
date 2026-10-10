# MEDIA Ω Architecture v0.1

## Goal

MEDIA Ω is not a "make N videos per day" bot. It is a goal-directed media operating system. Formats, platforms, topics, duration, and creative style are decisions made from evidence within policy and budget constraints.

## Canonical live intelligence path

There is exactly one live opportunity-decision path in the current Candidate:

YouTube read-only evidence → persisted observations → temporal momentum → age-normalized creator baseline v2 → peer-cohort diagnostics → IntelligenceSignal v4 → rank_signals → Orchestrator.choose_intelligence → EVIDENCE_COLLECTED → one policy-checked CreativePlan → PLANNED → one file-backed AssetManifest v2 → ASSETS_READY → one Verification Gate → VERIFIED.

The former parallel modules `intelligence.py`, `evaluation.py`, `ranking.py`, and `scoring.py` were retired. They must not be reintroduced as a second scoring brain. New live opportunity features must enter through the versioned canonical `IntelligenceSignal` contract and its evidence/tests.

Unknown creator history, malformed identity, sub-minute rate windows, unreliable temporal spacing, missing state, missing source provenance, non-finite JSON evidence, unsupported evidence, cross-entity evidence reuse, future evidence replay, or invalid workflow transitions fail closed. Scores are evidence-gated ranking signals, not probabilities or causal claims.

## Evidence and decision integrity

Evidence is journaled as a typed content-addressed receipt. Evidence v2 binds the evidence type and payload into the reference hash, preventing the same raw payload from silently changing semantic type.

The decision journal:
- serializes appends under a SQLite write transaction;
- rejects ordinary UPDATE and DELETE operations through database triggers;
- requires hashed fields on direct inserts;
- chains events with `prev_hash → event_hash`;
- verifies the chain before append/read operations;
- refuses to extend or consume a detected tampered chain.

This is tamper-evident and append-only at the enforced SQLite interface. It is not a claim that the database file is physically immutable against an administrator replacing the file.

## Workflow state engine

The centralized state machine enforces:

IDEA → EVIDENCE_COLLECTED → PLANNED → ASSETS_READY → VERIFIED → SCHEDULED → PUBLISHED → MEASURED → LEARNED

Terminal rejection/block paths are explicit and require a reason. State history is revalidated when read, including edge legality, contract version, field types, and evidence semantics.

Transition contracts currently require:
- every referenced evidence record to belong to the same workflow entity;
- evidence to exist in the journal before the transition event it authorizes, so later evidence cannot retroactively legitimize an earlier transition;
- EVIDENCE_COLLECTED: journal-verified canonical Intelligence evidence;
- PLANNED: matching typed creative-plan evidence whose payload records policy ACCEPT;
- ASSETS_READY: exactly one typed AssetManifest v2 bound to the admitted plan, with unique asset ids/paths, SHA256, positive byte size, media type, provider, and provenance;
- VERIFIED: typed verification evidence whose payload records ACCEPT and is bound to the exact plan and exact ASSETS_READY manifest;
- SCHEDULED: typed schedule evidence matching the schedule id;
- PUBLISHED: typed publication receipt whose payload confirms `published=true`;
- MEASURED: typed measurement evidence;
- LEARNED: typed learning evidence matching the learning version.

A dry-run receipt cannot satisfy the PUBLISHED contract even if a caller incorrectly passes a truthy flag.

## Control plane

### 1. Opportunity Intelligence
Collects permitted public signals, search/discovery provenance, trend velocity, creator history, and historical performance. Current YouTube creator baselines are age-normalized and source-referenced.

### 2. Peer Cohort / Outlier Context
Peer cohort v1 tracks query provenance, platform, content format when known, and explicit age comparability. Unknown format is surfaced as partial knowledge rather than silently treated as equivalent. Peer cohort data is currently diagnostic and does not silently rewrite the Intelligence v4 score.

### 3. Planning
Current minimal implementation. A selected opportunity can admit exactly one CreativePlan. The plan must pass the configured policy gate, is journaled as typed evidence, and then advances to PLANNED. A failed plan attempt leaves the selected opportunity retryable. Exact replay is idempotent; a changed plan cannot silently replace it. This gate validates plan declarations and budget/platform rules, not the final generated assets.

### 5. Creator Pipeline
Current minimal contract: one admitted plan is sent to one creator adapter with the plan id as an idempotency key. The adapter returns typed CreatedAsset values pointing at local files. MEDIA Ω independently resolves those files, rejects missing/empty output, computes SHA256 and byte size, and records one AssetManifest v2 with media type, provider, and provenance before ASSETS_READY is allowed. Current CI uses a deterministic local creator that writes real test files; no production generation provider is claimed yet.

### 6. Verification Gate
Implemented as one canonical gate. It resolves the exact admitted AssetManifest v2, rereads the real files, and checks entity/plan binding, existence, non-empty bytes, SHA256, size, media type, provenance, and a minimal platform-primary-media constraint. Only an ACCEPT verification.v1 receipt bound to that exact manifest can advance ASSETS_READY → VERIFIED. Missing, deleted, changed, malformed, or platform-incompatible assets fail closed and leave the workflow outside VERIFIED.

This gate proves concrete file/integrity/provenance properties only. It does not claim independent originality verification, ownership, licensing certainty, or copyright certainty.

### 7. Publisher
Not implemented for production. Future platform adapters must be idempotent, dry-run by default, rate-limit aware, and produce a publication receipt. Only a receipt that explicitly confirms publication can move the state machine to PUBLISHED.

### 8. Measurement
Future analytics ingestion. Measurements must be journaled as typed evidence before MEASURED.

### 9. Learning
Future versioned learning candidates. A single viral result may not rewrite global policy.

## Autonomy levels

- L0 Research only
- L1 Create drafts
- L2 Prepare publication, human approval required
- L3 Auto-publish within explicit platform/account/budget policy
- L4 Portfolio autonomy across approved accounts

Higher autonomy is earned through target tests and explicit capability grants; it is not inferred from green unit tests.

## Current proof boundary

The current deterministic E2E test covers:

Scout/discovery → enrichment → snapshots → two refreshes → creator baseline → momentum → Intelligence v4 → Orchestrator → typed evidence receipt → one CreativePlan → policy check → one deterministic creator → real local files → AssetManifest v2 with SHA256/size/provenance → ASSETS_READY → real file verification → verification.v1 → VERIFIED.

Candidate CI gates:
- Linux: Python 3.11, 3.12, 3.13, 3.14;
- Windows: Python 3.14;
- pinned pytest;
- dependency check;
- source compilation;
- full test suite.

The proof boundary stops at VERIFIED. Production media generation, Publisher, Measurement, and Learning are not yet proven or implemented as live production paths.
