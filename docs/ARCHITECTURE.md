# MEDIA Ω Architecture v0.1

## Goal

MEDIA Ω is not a "make N videos per day" bot. It is a goal-directed media operating system. Formats, platforms, topics, duration, and creative style are decisions made from evidence within policy and budget constraints.

## Canonical live intelligence path

There is exactly one live opportunity-decision path in the current Candidate:

YouTube read-only evidence → persisted observations → temporal momentum → age-normalized creator baseline v2 → peer-cohort diagnostics → IntelligenceSignal v4 → rank_signals → Orchestrator.choose_intelligence → journal evidence receipt → enforced EVIDENCE_COLLECTED state.

The former parallel modules `intelligence.py`, `evaluation.py`, `ranking.py`, and `scoring.py` were retired. They must not be reintroduced as a second scoring brain. New live opportunity features must enter through the versioned canonical `IntelligenceSignal` contract and its evidence/tests.

Unknown creator history, malformed identity, unreliable temporal spacing, missing state, missing source provenance, unsupported evidence, or invalid workflow transitions fail closed. Scores are evidence-gated ranking signals, not probabilities or causal claims.

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
- EVIDENCE_COLLECTED: journal-verified evidence;
- PLANNED: matching typed creative-plan evidence;
- ASSETS_READY: typed asset-manifest evidence containing assets;
- VERIFIED: typed verification evidence whose payload records ACCEPT;
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

### 3. Strategy / Portfolio Brain
Future layer. It may choose experiments across exploration/exploitation and platform/format, but it may not bypass canonical Intelligence v4 or the state/evidence contracts.

### 4. Creative Planner
Future layer. A plan may only advance the workflow when a typed creative-plan evidence receipt exists and matches the plan id.

### 5. Creator Pipeline
Future provider-neutral interfaces for text, image, video, audio, voice, editing, captions, thumbnails, and packaging.

### 6. Verification Gate
Current policy checks fail closed on originality/rights by default, required plan identity, platform allowance, and finite budget limits. Future media verification must produce typed evidence before VERIFIED can be entered.

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

Scout/discovery → enrichment → snapshots → two refreshes → creator baseline → momentum → Intelligence v4 → Orchestrator → typed evidence receipt → EVIDENCE_COLLECTED.

Candidate CI gates:
- Linux: Python 3.11, 3.12, 3.13, 3.14;
- Windows: Python 3.14;
- pinned pytest;
- dependency check;
- source compilation;
- full test suite.

The proof boundary stops before Strategy/Creator/real Publisher/Measurement/Learning implementation.
