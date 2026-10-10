import json
from io import BytesIO
from urllib.request import HTTPRedirectHandler

import pytest

from media_omega.youtube_api_readonly import YouTubeReadOnlyAPI, _NoRedirect
from media_omega.youtube_readback import verify_account, inspect_remote_video
from media_omega.youtube_upload_contract import UploadState, prepare_upload_intent


class FakeResponse:
    def __init__(self, data):
        self._stream = BytesIO(json.dumps(data).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n=-1):
        return self._stream.read(n)


class RecordingOpener:
    def __init__(self, data):
        self.data = data
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return FakeResponse(self.data)


def test_authenticated_account_read_uses_bearer_header_not_url():
    opener = RecordingOpener({"items": [{"id": "UC-owner"}]})
    api = YouTubeReadOnlyAPI("private-secret", opener=opener)
    assert api.get_authenticated_channel() == {"id": "UC-owner"}
    request, timeout = opener.calls[0]
    assert request.get_method() == "GET"
    assert "mine=true" in request.full_url
    assert "private-secret" not in request.full_url
    assert request.get_header("Authorization") == "Bearer private-secret"
    assert verify_account(api, "UC-owner").state is UploadState.NOT_STARTED


def test_remote_video_read_maps_youtube_fields():
    opener = RecordingOpener({"items": [{
        "id": "vid1",
        "snippet": {"channelId": "UC-owner"},
        "status": {"privacyStatus": "private"},
    }]})
    api = YouTubeReadOnlyAPI("secret", opener=opener)
    assert api.get_video("vid1") == {
        "id": "vid1", "channel_id": "UC-owner", "privacy_status": "private",
    }
    req, _ = opener.calls[0]
    assert "part=snippet%2Cstatus" in req.full_url


def test_api_rejects_malformed_or_missing_responses():
    for data in [{"items": []}, {"items": [{"id": "a"}, {"id": "b"}]}, {}]:
        with pytest.raises(RuntimeError):
            YouTubeReadOnlyAPI("x", opener=RecordingOpener(data)).get_authenticated_channel()
    for data in [{"items": [1]}, {"items": [{ "id": "x"}]}, {"items": [1, 2]}]:
        with pytest.raises(RuntimeError):
            YouTubeReadOnlyAPI("x", opener=RecordingOpener(data)).get_video("x")
    assert YouTubeReadOnlyAPI("x", opener=RecordingOpener({"items": []})).get_video("x") is None


def test_no_redirect_and_only_whitelisted_paths():
    assert _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil") is None
    api = YouTubeReadOnlyAPI("secret", opener=RecordingOpener({}))
    with pytest.raises(ValueError, match="not allowed"):
        api._get("videos/insert", {})
    with pytest.raises(ValueError, match="not allowed"):
        api._get("https://example.com", {})


def test_readback_cannot_claim_upload_success():
    channel = RecordingOpener({"items": [{"id": "UC-owner"}]})
    assert verify_account(YouTubeReadOnlyAPI("secret", opener=channel), "UC-owner").reason == "CHANNEL_READ_CONFIRMED"
    video = RecordingOpener({"items": []})
    api = YouTubeReadOnlyAPI("secret", opener=video)
    intent = prepare_upload_intent({
        "version": "schedule.v2", "platform": "youtube", "visibility": "private",
        "dry_run_only": True, "entity_id": "youtube:one",
        "schedule_id": "schedule-1", "plan_id": "plan-1",
        "manifest_ref": "manifest", "verification_ref": "verify",
    }, channel_id="UC-owner", expected_channel_id="UC-owner", asset_sha256="a" * 64)
    result = inspect_remote_video(api, intent, "missing")
    assert result.state is UploadState.REMOTE_UNKNOWN


def test_public_chart_api_key_uses_get_only_and_never_bearer():
    opener = RecordingOpener({"items": [{"id": "ABC123", "snippet": {"title": "A", "channelId": "UC"}, "statistics": {"viewCount": "123"}}]})
    api = YouTubeReadOnlyAPI(api_key="temporary-key", opener=opener)
    rows = api.get_popular_videos(region_code="TH", max_results=10)
    assert rows[0]["views"] == 123
    assert rows[0]["reuse_permission"] == "NOT_VERIFIED"
    request, _ = opener.calls[0]
    assert request.get_method() == "GET"
    assert "chart=mostPopular" in request.full_url
    assert "regionCode=TH" in request.full_url
    assert "key=temporary-key" in request.full_url
    assert request.get_header("Authorization") is None


def test_api_key_does_not_unlock_account_or_nonpublic_read():
    api = YouTubeReadOnlyAPI(api_key="temporary-key", opener=RecordingOpener({}))
    with pytest.raises(ValueError, match="OAuth"):
        api.get_authenticated_channel()
    with pytest.raises(ValueError, match="public popular"):
        api.get_video("an-id")
    with pytest.raises(ValueError, match="credential"):
        YouTubeReadOnlyAPI()
