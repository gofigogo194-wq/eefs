"""YouTube upload protocol design: pure validation, NO HTTP, NO credentials.

A remote write is NEVER safe to retry merely because its response timed out.
The only allowed next action for an uncertain write is operator reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json


class UploadState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    SUBMITTING = "SUBMITTING"
    REMOTE_UNKNOWN = "REMOTE_UNKNOWN"
    REMOTE_CONFIRMED_PRIVATE = "REMOTE_CONFIRMED_PRIVATE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class UploadIntent:
    entity_id: str
    schedule_id: str
    plan_id: str
    channel_id: str
    manifest_ref: str
    verification_ref: str
    asset_sha256: str
    visibility: str
    identity_key: str
    version: str = "youtube_upload_intent.v1"


def prepare_upload_intent(schedule: dict, *, channel_id: str,
                          expected_channel_id: str, asset_sha256: str) -> UploadIntent:
    """Build a deterministic binding; it DOES NOT approve upload execution."""
    if (
        not isinstance(schedule, dict)
        or schedule.get("version") != "schedule.v2"
        or schedule.get("platform") != "youtube"
        or schedule.get("visibility") != "private"
        or schedule.get("dry_run_only") is not True
    ):
        raise ValueError("canonical private dry-run schedule required")
    for field in ("entity_id", "schedule_id", "plan_id", "manifest_ref", "verification_ref"):
        if not isinstance(schedule.get(field), str) or not schedule[field].strip():
            raise ValueError(f"{field} is required")
    if (
        not isinstance(channel_id, str)
        or not channel_id.strip()
        or not isinstance(expected_channel_id, str)
        or channel_id != expected_channel_id
    ):
        raise ValueError("channel identity mismatch")
    if not isinstance(asset_sha256, str) or len(asset_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in asset_sha256
    ):
        raise ValueError("invalid media digest")
    binding = {
        "entity_id": schedule["entity_id"],
        "schedule_id": schedule["schedule_id"],
        "plan_id": schedule["plan_id"],
        "channel_id": channel_id,
        "manifest_ref": schedule["manifest_ref"],
        "verification_ref": schedule["verification_ref"],
        "asset_sha256": asset_sha256,
        "visibility": "private",
    }
    key = sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return UploadIntent(**binding, identity_key=key)


def reconcile_upload_outcome(state: UploadState, *, remote_video_id: str | None = None,
                             verified_channel_id: str | None = None,
                             intent: UploadIntent | None = None) -> UploadState:
    """Pure recovery policy; never reissues a write or claims server confirmation."""
    if state is UploadState.SUBMITTING:
        return UploadState.REMOTE_UNKNOWN
    if state is UploadState.REMOTE_UNKNOWN:
        # External confirmation must go through a future authenticated readback;
        # caller supplied IDs alone are insufficient evidence.
        return UploadState.REMOTE_UNKNOWN
    if state is UploadState.NOT_STARTED and remote_video_id is not None:
        raise ValueError("remote result without a submitted request")
    return state


def may_retry_upload(state: UploadState) -> bool:
    """Conservative safety contract; actual upload capability is absent."""
    return False
