# MEDIA Ω Architecture v0.1

## Goal

MEDIA Ω is not a "make N videos per day" bot. It is a goal-directed media operating system. Formats, platforms, topics, duration, and creative style are decisions made from evidence within policy and budget constraints.

## Canonical live intelligence path

There is exactly one live opportunity-decision path:

YouTube read-only evidence → persisted observations → temporal momentum → age-normalized creator baseline v2 → IntelligenceSignal v3 → rank_signals → Orchestrator.choose_intelligence.

The former parallel modules `intelligence.py`, `evaluation.py`, `ranking.py`, and `scoring.py` were retired from the Candidate branch. They must not be reintroduced as a second scoring brain. New opportunity features must enter through the versioned canonical `IntelligenceSignal` contract and its evidence/tests.

Unknown creator history, malformed identity, unreliable temporal spacing, missing state, and unsupported evidence fail closed. Scores are evidence-gated ranking signals, not probabilities or causal claims.

## Control plane

### 1. Opportunity Intelligence
Collects permitted public signals, channel/account analytics, search demand, trend velocity, and historical performance. Produces normalized opportunities with provenance and uncertainty.

### 2. Outlier Engine
Separates raw popularity from abnormal performance. Candidate features include:
- performance relative to an age-normalized creator/channel baseline;
- velocity and acceleration;
- age-normalized engagement;
- saturation/competition;
- production cost;
- fit with available capabilities;
- evidence quality.

It never treats a viral item as content to copy.

### 3. Strategy / Portfolio Brain
Chooses experiments across exploration and exploitation. It may select long-form, Shorts, Reels, images, audio-led content, or reject all opportunities when expected value is poor. This layer is not yet a production implementation and may not bypass canonical Intelligence v3.

### 4. Creative Planner
Turns an opportunity into an original creative brief with audience, hook, format, asset plan, metadata hypotheses, budget, and success/failure criteria.

### 5. Creator Pipeline
Provider-neutral interfaces for text, image, video, audio, voice, editing, captions, thumbnails, and packaging. Provider choice is configuration, not core logic.

### 6. Verification Gate
Checks provenance, originality/authorization, media integrity, platform constraints, metadata, duration/aspect ratio, budget, and configured policy rules before an artifact becomes publishable.

### 7. Publisher
Platform adapters with idempotency, dry-run by default, scheduling, retries, rate-limit handling, and immutable publication receipts. OAuth/API credentials stay outside source control.

### 8. Measurement
Ingests impressions/reach, CTR where available, retention/watch time, engagement, subscribers/followers, traffic sources, revenue when available, and production cost. Raw observations are immutable.

### 9. Learning
Compares hypotheses with outcomes. Strategy updates are versioned; no single viral result is allowed to rewrite the global policy.

## State model

IDEA → EVIDENCE_COLLECTED → PLANNED → ASSETS_READY → VERIFIED → SCHEDULED → PUBLISHED → MEASURED → LEARNED

Any state may transition to REJECTED or BLOCKED with a reason.

## Autonomy levels

- L0 Research only
- L1 Create drafts
- L2 Prepare publication, human approval required
- L3 Auto-publish within explicit platform/account/budget policy
- L4 Portfolio autonomy across approved accounts

Bootstrap begins at L0/L1. Higher levels are earned by tests and explicit account capability grants.

## Initial implementation slices

1. Domain contracts + SQLite event/decision journal.
2. Canonical age-normalized opportunity intelligence with deterministic fixtures.
3. Peer cohort provenance and comparability.
4. Strategy portfolio selector.
5. Creator provider interfaces and local fake providers.
6. Verification gate.
7. Publisher dry-run + idempotency.
8. YouTube private/unlisted test adapter.
9. Analytics ingestion.
10. Closed-loop shadow run before any L3 autonomy.
