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

DISCOVER → OBSERVE → COMPARE → SELECT → PLAN + POLICY CHECK → CREATE → ASSETS_READY

PLAN + POLICY CHECK is deliberately one step: one selected opportunity gets one exact plan. If the plan declarations, platform, required fields, or budget fail, that plan attempt is rejected and the selected opportunity stays retryable. If they pass, the exact plan is journaled and the workflow reaches PLANNED. This is not yet proof that generated assets are original or licensed; actual asset verification stays after creation.

The creator boundary is now enforced as one path: an admitted plan is passed to one creator adapter with the plan id as the idempotency key; one typed asset manifest is recorded; only then can the workflow reach ASSETS_READY. The current tests use a deterministic fake creator, so this proves the contract and recovery behavior, not a production media-generation provider.

Final asset verification, publishing, measurement, and learning remain future stages. They must extend the same linear flow instead of creating parallel systems.
