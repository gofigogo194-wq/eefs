# MEDIA Ω — one working automatic-channel path (Candidate scope)

## Target outcome
Find relevant public examples -> select idea -> generate an original/licensed local MP4 -> inspect real file -> upload to the user's explicitly connected YouTube channel -> reconcile remote outcome -> record performance. No duplicate agents, new parallel engine, or scraping/republishing third-party media.

## Scope of the current WIP = 1: authenticated private upload
The desktop currently proves topic discovery on real YouTube and local video output on the target Windows PC. Upload remains **NOT IMPLEMENTED**. The next candidate extends the existing publisher boundary, not a parallel publisher:
1. Desktop user explicitly connects a Google OAuth account with upload scope. API key cannot publish; authenticate separately. Verify the expected channel identity before any network write, and keep permissions minimal.
2. Supply a locally verified, authorized MP4; bind canonical source path + SHA256 + intended channel ID + metadata to a durable upload intent. No source changes after verification. Require truthful rights/originality declarations; do not infer rights from popular-video search results.
3. Default every first network upload to **private**. No public write or automatic scheduling until the operator has reviewed a successfully uploaded private sample on their real channel and deliberately enabled it.
4. Start one resumable upload session and durably record the state before contacting YouTube. On timeout, crash, restart, missing receipt, wrong account, or uncertain response: mark REMOTE_UNKNOWN and STOP. Never blindly re-upload or publish duplicate videos.
5. Confirm returned video identifier and authorized channel through authenticated provider readback; distinguish remote metadata from byte-level proof. An ambiguous remote outcome must be reconciled rather than declared successful.
6. Enforce media probe and complete decode as a mandatory gate. Prevent stale/changed files, invalid output, wrong channel, duplicate job, unsafe rights assumptions and unverified upload metadata.
7. Tests: invalid/wrong Google identity; expired credentials; scope denial; malformed response; upload initiation / chunks; resume / restart; network cut before/after remote commit; idempotency; no public write by default; no secret in logs; real target Windows private upload and readback. Run all CI and artifact-rebuild verification before release.

## Subsequent stages, not current WIP
After private-upload E2E PASS: an explicit opt-in auto-publication/scheduling mode, queue of already-authorized sources, per-day limit, no duplicate uploads, quality/policy gate, and stop switch. Only then autonomous discovery-to-publish orchestration. Measurement learns from factual time-separated observations; no claims of predicted success.

## Hard safety/policy boundaries
- Public YouTube search is **reference only**, not permission to download or republish.
- Minor edits to someone else's video and mass-produced repetitive variants can violate YouTube's reused/inauthentic-content monetization policies, even when rights are granted.
- Default DENY upload with missing user account authorization, licensing proof or rights declaration, missing confirmed channel binding, or unresolved intent.
- Do not log or persist raw access/refresh tokens or authorization codes in journal/CI. A secure credential store is required before persistent unattended OAuth refresh.
- Real publication is not proven by a mocked upload test, local receipt, or API key.
- Champion stays immutable; this document is a plan, not an implemented feature.

## User acceptance
On Windows: connect intended channel, render sample from user-owned video and music, upload **private** once, see correct private video on expected channel, restart app without duplicate, review result. Only then consider explicit opt-in automatic public uploading.
