from media_omega.youtube_readback import verify_account, inspect_remote_video
from media_omega.youtube_upload_contract import (
    UploadState, prepare_upload_intent, may_retry_upload,
)


def schedule():
    return {
        "version": "schedule.v2", "platform": "youtube", "visibility": "private",
        "dry_run_only": True, "entity_id": "youtube:one",
        "schedule_id": "schedule-abc", "plan_id": "plan",
        "manifest_ref": "manifest", "verification_ref": "verified",
    }


class FakeReadOnly:
    def __init__(self, channel="UC-owner", video=None, error=False):
        self.channel = channel
        self.video = video
        self.error = error
        self.reads = []

    def get_authenticated_channel(self):
        self.reads.append("channel")
        if self.error:
            raise TimeoutError("auth unavailable")
        return {"id": self.channel}

    def get_video(self, video_id):
        self.reads.append(("video", video_id))
        if self.error:
            raise TimeoutError("read unavailable")
        return self.video


def intent():
    return prepare_upload_intent(
        schedule(), channel_id="UC-owner",
        expected_channel_id="UC-owner", asset_sha256="a" * 64,
    )


def test_account_check_accepts_only_matching_authenticated_channel():
    valid = verify_account(FakeReadOnly(), "UC-owner")
    assert valid.reason == "CHANNEL_READ_CONFIRMED"
    assert valid.channel_id == "UC-owner"
    assert verify_account(FakeReadOnly("UC-other"), "UC-owner").state is UploadState.BLOCKED
    assert verify_account(FakeReadOnly(error=True), "UC-owner").state is UploadState.BLOCKED


def test_missing_remote_video_cannot_trigger_retry():
    transport = FakeReadOnly()
    result = inspect_remote_video(transport, intent(), "missing")
    assert result.state is UploadState.REMOTE_UNKNOWN
    assert result.reason == "REMOTE_VIDEO_NOT_FOUND"
    assert may_retry_upload(result.state) is False


def test_matching_metadata_not_proof_of_uploaded_asset():
    video = {"id": "vid-123", "channel_id": "UC-owner", "privacy_status": "private"}
    result = inspect_remote_video(FakeReadOnly(video=video), intent(), "vid-123")
    assert result.reason == "REMOTE_PRIVATE_METADATA_MATCH_ONLY"
    assert result.state is UploadState.REMOTE_UNKNOWN
    assert result.video_id == "vid-123"


def test_untrusted_foreign_or_public_video_does_not_confirm():
    for video in (
        {"id": "vid-123", "channel_id": "UC-other", "privacy_status": "private"},
        {"id": "vid-123", "channel_id": "UC-owner", "privacy_status": "public"},
        {"id": "different", "channel_id": "UC-owner", "privacy_status": "private"},
    ):
        result = inspect_remote_video(FakeReadOnly(video=video), intent(), "vid-123")
        assert result.state is UploadState.REMOTE_UNKNOWN
        assert result.reason == "REMOTE_VIDEO_BINDING_MISMATCH"


def test_channel_mismatch_skips_video_read():
    transport = FakeReadOnly(channel="UC-foreign")
    result = inspect_remote_video(transport, intent(), "vid-123")
    assert result.state is UploadState.REMOTE_UNKNOWN
    assert transport.reads == ["channel"]
