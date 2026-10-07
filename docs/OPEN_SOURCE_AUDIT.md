# Open-source reconnaissance — 2026-10-07

This is a preliminary architectural screen, not a security certification.

## Nuraveda-Labs/ai-social-agent

**License:** MIT (repository claim)

**Observed capabilities:** signal scouting, platform-specific script/caption generation, pluggable video generation, publishing to YouTube Shorts / Instagram Reels / X / LinkedIn, ORM, pacing, and a human approval gate.

**Take / adapt concepts:** modular scout→creative→publisher pipeline; provider abstraction; explicit pacing; approval/safety boundary.

**Do not assume:** production maturity, correctness, security, or suitability merely from README. The repository is young and must be source-audited before code adoption.

## Postiz

**License:** AGPL-3.0.

**Observed capabilities:** broad social scheduling, analytics, public API/SDK, automation integrations, OAuth-based platform connections.

**Use:** strong candidate as an external publishing/scheduling service or architectural reference.

**License boundary:** do not copy AGPL source into MEDIA Ω without deliberately accepting AGPL obligations. Prefer a service/API boundary while we decide licensing.

## Decision

Do not import a large third-party codebase into the empty repository yet. First build the small MEDIA Ω control-plane contracts and test harness. Third-party systems should be replaceable adapters. This prevents our strategy/memory/learning brain from becoming coupled to a publisher or a video generator.

## Next audit

Source-level review of candidate repositories for:
- dependency and secret handling;
- OAuth/token storage;
- actual publisher implementations vs README claims;
- retry/idempotency semantics;
- data models and migrations;
- tests and CI;
- media provenance and copyright controls;
- platform API compliance;
- failure behavior.
