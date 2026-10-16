"""Read-only provider boundary for YouTube account and upload reconciliation.

The supplied transport can ONLY perform two authenticated reads. No upload,
patch, delete, or remote mutation method is part of the interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .youtube_upload_contract import UploadIntent, UploadState


class ReadOnlyYouTubeTransport(Protocol):
    def get_authenticated_channel(self) -> dict: ...
    def get_video(self, video_id: str) -> dict | None: ...


@dataclass(frozen=True)
class RemoteCheck:
    state: UploadState
    reason: str
    channel_id: str = ""
    video_id: str = ""


def verify_account(transport: ReadOnlyYouTubeTransport, expected_channel_id: str) -> RemoteCheck:
    if not isinstance(expected_channel_id, str) or not expected_channel_id.strip():
        return RemoteCheck(UploadState.BLOCKED, "EXPECTED_CHANNEL_REQUIRED")
    try:
        response = transport.get_authenticated_channel()
    except Exception:
        return RemoteCheck(UploadState.BLOCKED, "AUTHENTICATED_CHANNEL_READ_FAILED")
    if (
        not isinstance(response, dict)
        or not isinstance(response.get("id"), str)
        or not response["id"].strip()
        or response.get("id") != expected_channel_id
    ):
        return RemoteCheck(UploadState.BLOCKED, "AUTHENTICATED_CHANNEL_MISMATCH")
    return RemoteCheck(UploadState.NOT_STARTED, "CHANNEL_READ_CONFIRMED", channel_id=response["id"])


def inspect_remote_video(
    transport: ReadOnlyYouTubeTransport, intent: UploadIntent,
    remote_video_id: str | None,
) -> RemoteCheck:
    """Read-only investigation. Never authorizes retries or a PUBLISHED state."""
    if not isinstance(intent, UploadIntent):
        return RemoteCheck(UploadState.REMOTE_UNKNOWN, "INVALID_INTENT")
    account = verify_account(transport, intent.channel_id)
    if account.state is UploadState.BLOCKED:
        return RemoteCheck(UploadState.REMOTE_UNKNOWN, account.reason)
    if not isinstance(remote_video_id, str) or not remote_video_id.strip():
        return RemoteCheck(UploadState.REMOTE_UNKNOWN, "REMOTE_VIDEO_ID_UNKNOWN")
    try:
        response = transport.get_video(remote_video_id)
    except Exception:
        return RemoteCheck(UploadState.REMOTE_UNKNOWN, "REMOTE_READ_FAILED")
    if response is None:
        # Not found is not proof of a failed upload: eventual consistency,
        # permission problems, or a different video ID may be involved.
        return RemoteCheck(UploadState.REMOTE_UNKNOWN, "REMOTE_VIDEO_NOT_FOUND")
    if not isinstance(response, dict):
        return RemoteCheck(UploadState.REMOTE_UNKNOWN, "REMOTE_PAYLOAD_INVALID")
    if (
        response.get("id") != remote_video_id
        or response.get("channel_id") != intent.channel_id
        or response.get("privacy_status") != "private"
    ):
        return RemoteCheck(UploadState.REMOTE_UNKNOWN, "REMOTE_VIDEO_BINDING_MISMATCH")
    # This confirms limited metadata for an identified private video. It
    # does NOT prove matching bytes or that the planned upload created it.
    return RemoteCheck(
        UploadState.REMOTE_UNKNOWN, "REMOTE_PRIVATE_METADATA_MATCH_ONLY",
        channel_id=intent.channel_id, video_id=remote_video_id,
    )
