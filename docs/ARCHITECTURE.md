# MEDIA Ω Architecture v0.1

## Goal

MEDIA Ω is not a "make N videos per day" bot. It is a goal-directed media operating system. Formats, platforms, topics, duration, and creative style are decisions made from evidence within policy and budget constraints.

## Control plane

### 1. Opportunity Intelligence
Collects permitted public signals, channel/account analytics, search demand, trend velocity, and historical performance. Produces normalized opportunities with provenance and uncertainty.

### 2. Outlier Engine
Separates raw popularity from abnormal performance. Candidate features include:
- performance relative to a creator/channel baseline;
- velocity and acceleration;
- age-normalized engagement;
- saturation/competition;
- production cost;
- fit with available capabilities;
- evidence quality.

It never treats a viral item as content to copy.

### 3. Strategy / Portfolio Brain
Chooses experiments across exploration and exploitation. It may select long-form, Shorts, Reels, images, audio-led content, or reject all opportunities when expected value is poor.

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
2. Opportunity/outlier engine with deterministic fixtures.
3. Strategy portfolio selector.
4. Creator provider interfaces and local fake providers.
5. Verification gate.
6. Publisher dry-run + idempotency.
7. YouTube private/unlisted test adapter.
8. Analytics ingestion.
9. Closed-loop shadow run before any L3 autonomy.
