import json
from io import BytesIO
import pytest

from media_omega.youtube_private_upload import PrivateUpload
from media_omega.models import Decision, GateResult


@pytest.fixture(autouse=True)
def verified_media(monkeypatch):
    from media_omega import media_probe
    monkeypatch.setattr(media_probe, "inspect_video", lambda path: (
        GateResult(Decision.ACCEPT, ("OK",)), {"audio_present": True}))
    monkeypatch.setattr(media_probe, "decode_video", lambda path, timeout: (
        GateResult(Decision.ACCEPT, ("OK",))))


class Reply:
    def __init__(self, payload, location=None):
        self.raw = BytesIO(json.dumps(payload).encode())
        self.headers = {"Location": location} if location else {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        return self.raw.read(n)


class Opener:
    def __init__(self, failure=False):
        self.calls = []
        self.failure = failure
    def open(self, request, timeout):
        self.calls.append(request)
        if self.failure:
            raise TimeoutError("simulated remote uncertainty")
        if request.get_method() == "POST":
            metadata = json.loads(request.data)
            assert metadata["status"]["privacyStatus"] == "private"
            return Reply({}, "https://www.googleapis.com/upload/youtube/v3/videos/session")
        assert request.get_method() == "PUT"
        return Reply({"id": "video-abc", "status": {"privacyStatus": "private"},
                      "snippet": {"channelId": "UC-owner"}})


def test_private_upload_is_one_shot_and_never_public(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    op = Opener()
    client = PrivateUpload(str(tmp_path / "state"), opener=op)
    result = client.upload_once(str(media), access_token="test-token",
                                channel_id="UC-owner", title="Sample",
                                rights_confirmed=True, preflight=lambda path: True)
    assert result["state"] == "REMOTE_UNKNOWN"
    assert len(op.calls) == 2
    assert op.calls[1].data == b"test media"
    assert len(list((tmp_path / "state").glob("*.json"))) == 1
    with pytest.raises(RuntimeError, match="already attempted"):
        client.upload_once(str(media), access_token="test-token",
                           channel_id="UC-owner", title="Sample",
                           rights_confirmed=True, preflight=lambda path: True)
    assert len(op.calls) == 2


def test_unknown_outcome_stays_locked_on_restart(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    op = Opener(failure=True)
    with pytest.raises(RuntimeError, match="outcome unknown"):
        PrivateUpload(str(tmp_path / "state"), opener=op).upload_once(
            str(media), access_token="token", channel_id="UC-owner",
            title="Sample", rights_confirmed=True, preflight=lambda path: True)
    with pytest.raises(RuntimeError, match="already attempted"):
        PrivateUpload(str(tmp_path / "state"), opener=Opener()).upload_once(
            str(media), access_token="token", channel_id="UC-owner",
            title="Sample", rights_confirmed=True, preflight=lambda path: True)


def test_preflight_rejection_never_contacts_youtube(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    opener = Opener()
    client = PrivateUpload(str(tmp_path / "state"), opener=opener)
    with pytest.raises(ValueError, match="preflight"):
        client.upload_once(str(media), access_token="token", channel_id="UC-owner",
                           title="Sample", rights_confirmed=True, preflight=lambda path: False)
    assert not opener.calls
