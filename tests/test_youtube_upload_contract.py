import pytest

from media_omega.youtube_upload_contract import (
    UploadState, prepare_upload_intent, reconcile_upload_outcome, may_retry_upload,
)


def schedule():
    return {
        "version": "schedule.v2", "platform": "youtube", "visibility": "private",
        "dry_run_only": True, "entity_id": "youtube:one",
        "schedule_id": "schedule-abc", "plan_id": "p1",
        "manifest_ref": "manifest-ref", "verification_ref": "verify-ref",
    }


def test_upload_intent_deterministic_but_not_authorization():
    args = {"channel_id": "UC-confirmed", "expected_channel_id": "UC-confirmed",
            "asset_sha256": "a" * 64}
    first = prepare_upload_intent(schedule(), **args)
    second = prepare_upload_intent(schedule(), **args)
    assert first == second
    assert first.visibility == "private"
    assert len(first.identity_key) == 64
    assert may_retry_upload(UploadState.NOT_STARTED) is False


@pytest.mark.parametrize("change", [
    {"visibility": "public"}, {"version": "schedule.v1"},
    {"dry_run_only": False}, {"platform": "other"},
    {"manifest_ref": ""}, {"verification_ref": ""},
])
def test_untrusted_schedule_fails_closed(change):
    with pytest.raises(ValueError):
        prepare_upload_intent(
            {**schedule(), **change}, channel_id="UC-a",
            expected_channel_id="UC-a", asset_sha256="a" * 64,
        )


def test_channel_mismatch_and_digest_block():
    with pytest.raises(ValueError, match="channel identity mismatch"):
        prepare_upload_intent(
            schedule(), channel_id="UC-attacker",
            expected_channel_id="UC-owner", asset_sha256="a" * 64,
        )
    with pytest.raises(ValueError, match="digest"):
        prepare_upload_intent(
            schedule(), channel_id="UC-owner",
            expected_channel_id="UC-owner", asset_sha256="not-a-hash",
        )


def test_remote_timeout_always_ambiguous_and_never_retryable():
    assert reconcile_upload_outcome(UploadState.SUBMITTING) is UploadState.REMOTE_UNKNOWN
    assert reconcile_upload_outcome(
        UploadState.REMOTE_UNKNOWN, remote_video_id="claimed-video",
        verified_channel_id="UC-owner",
    ) is UploadState.REMOTE_UNKNOWN
    for state in UploadState:
        assert may_retry_upload(state) is False
    with pytest.raises(ValueError, match="without a submitted"):
        reconcile_upload_outcome(UploadState.NOT_STARTED, remote_video_id="untrusted")


def test_binding_changes_with_channel_or_asset():
    a = prepare_upload_intent(schedule(), channel_id="UC-a",
                              expected_channel_id="UC-a", asset_sha256="a" * 64)
    b = prepare_upload_intent(schedule(), channel_id="UC-b",
                              expected_channel_id="UC-b", asset_sha256="a" * 64)
    c = prepare_upload_intent(schedule(), channel_id="UC-a",
                              expected_channel_id="UC-a", asset_sha256="b" * 64)
    assert len({a.identity_key, b.identity_key, c.identity_key}) == 3


def test_private_preflight_rejects_wrong_channel_rights_and_digest(tmp_path):
    from media_omega.youtube_upload_contract import verify_private_upload_source
    from hashlib import sha256
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"fixture")
    intent = prepare_upload_intent(
        schedule(), channel_id="UC-owner",
        expected_channel_id="UC-owner",
        asset_sha256=sha256(b"fixture").hexdigest(),
    )
    with pytest.raises(ValueError, match="rights"):
        verify_private_upload_source(intent, str(video), confirmed_channel_id="UC-owner",
                                     rights_confirmed=False)
    with pytest.raises(ValueError, match="channel"):
        verify_private_upload_source(intent, str(video), confirmed_channel_id="UC-foreign",
                                     rights_confirmed=True)
    video.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="digest"):
        verify_private_upload_source(intent, str(video), confirmed_channel_id="UC-owner",
                                     rights_confirmed=True)


def test_private_preflight_inspects_actual_file_without_upload(tmp_path, monkeypatch):
    from hashlib import sha256
    from media_omega import media_probe
    from media_omega.youtube_upload_contract import verify_private_upload_source
    from media_omega.models import Decision, GateResult
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"video-sample")
    intent = prepare_upload_intent(
        schedule(), channel_id="UC-owner", expected_channel_id="UC-owner",
        asset_sha256=sha256(video.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(media_probe, "inspect_video", lambda path: (
        GateResult(Decision.ACCEPT, ("OK",)),
        {"audio_present": True, "duration_seconds": 60, "video_codec": "h264"},
    ))
    monkeypatch.setattr(media_probe, "decode_video", lambda path, timeout: (
        GateResult(Decision.ACCEPT, ("OK",))
    ))
    facts = verify_private_upload_source(
        intent, str(video), confirmed_channel_id="UC-owner", rights_confirmed=True,
    )
    assert facts["published"] is False
    assert facts["visibility"] == "private"
    assert facts["channel_id"] == "UC-owner"
    assert facts["size_bytes"] == len(b"video-sample")
