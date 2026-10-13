"""Mocked transport contract; CI also runs real ffprobe/ffmpeg integration tests."""
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import json

import pytest
from media_omega.youtube_private_upload import PrivateUpload
from media_omega.models import Decision, GateResult

VIDEO_ID = "abc12345678"
CHANNEL = "UC-owner"


@pytest.fixture(autouse=True)
def verified_media(monkeypatch):
    from media_omega import media_probe
    monkeypatch.setattr(media_probe, "inspect_video", lambda path: (
        GateResult(Decision.ACCEPT, ("OK",)), {"audio_present": True}))
    monkeypatch.setattr(media_probe, "decode_video", lambda path, timeout: (
        GateResult(Decision.ACCEPT, ("OK",))))


class Reply:
    def __init__(self, payload, *, code=200, headers=None):
        self.raw = BytesIO(json.dumps(payload).encode() if isinstance(payload, dict) else payload)
        self.headers = headers or {}
        self.code = code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return self.raw.read(n)

    def getcode(self):
        return self.code


class Opener:
    def __init__(self, *, fail_post=False, channel=CHANNEL, readback_private=True,
                 session_url="https://www.googleapis.com/upload/youtube/v3/videos?upload_id=demo",
                 mutate_after_post=None, bad_ack=False):
        self.calls = []
        self.fail_post = fail_post
        self.channel = channel
        self.readback_private = readback_private
        self.session_url = session_url
        self.mutate_after_post = mutate_after_post
        self.bad_ack = bad_ack
        self.acked = 0

    def open(self, request, timeout):
        self.calls.append(request)
        method = request.get_method()
        url = urlsplit(request.full_url)
        if method == "GET":
            if url.path.endswith("/channels"):
                return Reply({"items": [{"id": self.channel}]})
            if url.path.endswith("/videos"):
                assert parse_qs(url.query)["id"] == [VIDEO_ID]
                assert "maxResults" not in parse_qs(url.query)
                return Reply({"items": [{"id": VIDEO_ID, "snippet": {"channelId": self.channel},
                                         "status": {"privacyStatus":
                                                    "private" if self.readback_private else "public"}}]})
        if method == "POST":
            assert json.loads(request.data)["status"]["privacyStatus"] == "private"
            if self.fail_post:
                raise TimeoutError("uncertain POST")
            if self.mutate_after_post:
                self.mutate_after_post()
            return Reply(b"", headers={"Location": self.session_url})
        if method == "PUT":
            start_end, total = request.headers["Content-range"].removeprefix("bytes ").split("/")
            start, end = map(int, start_end.split("-"))
            assert start == self.acked
            assert end + 1 == start + len(request.data)
            assert int(total) >= end + 1
            self.acked = end + 1
            if self.acked < int(total):
                header = {"Range": ("bytes=0-" + str(end - 1)) if self.bad_ack
                          else ("bytes=0-" + str(end))}
                raise HTTPError(request.full_url, 308, "Resume Incomplete", header, BytesIO())
            return Reply({"id": VIDEO_ID, "status": {"privacyStatus": "private"},
                          "snippet": {"channelId": CHANNEL}}, code=201)
        raise AssertionError("unexpected transport operation")


def upload(media: Path, state: Path, opener: Opener):
    return PrivateUpload(str(state), opener=opener).upload_once(
        str(media), access_token="test-token", channel_id=CHANNEL,
        title="Original Ambient", description="Licensed audio and video",
        rights_confirmed=True, preflight=lambda path: True)


def marker(state: Path):
    files = list(state.glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text())


def test_private_upload_requires_two_authenticated_reads_and_durable_confirmation(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    state = tmp_path / "attempts"
    opener = Opener()
    result = upload(media, state, opener)
    assert result == {"video_id": VIDEO_ID, "state": "REMOTE_CONFIRMED_PRIVATE",
                      "url": "https://www.youtube.com/watch?v=" + VIDEO_ID,
                      "channel_id": CHANNEL}
    assert [r.get_method() for r in opener.calls] == ["GET", "POST", "PUT", "GET", "GET"]
    assert marker(state)["state"] == "REMOTE_CONFIRMED_PRIVATE"
    assert marker(state)["video_id"] == VIDEO_ID
    assert "test-token" not in list(state.glob("*.json"))[0].read_text()
    with pytest.raises(RuntimeError, match="already attempted"):
        upload(media, state, Opener())


def test_chunked_upload_uses_308_ack_and_bounded_buffer(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"x" * (2 * 256 * 1024 + 21))
    state = tmp_path / "attempts"
    opener = Opener()
    client = PrivateUpload(str(state), opener=opener)
    client.CHUNK_BYTES = 256 * 1024
    assert client.upload_once(str(media), access_token="test-token", channel_id=CHANNEL,
                              title="test", rights_confirmed=True,
                              preflight=lambda path: True)["state"] == "REMOTE_CONFIRMED_PRIVATE"
    chunks = [r.data for r in opener.calls if r.get_method() == "PUT"]
    assert len(chunks) == 3
    assert max(map(len, chunks)) == 256 * 1024
    assert b"".join(chunks) == media.read_bytes()


def test_unknown_outcome_stays_locked_after_restart(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    state = tmp_path / "attempts"
    with pytest.raises(RuntimeError, match="outcome unknown"):
        upload(media, state, Opener(fail_post=True))
    assert marker(state)["state"] == "REMOTE_UNKNOWN"
    with pytest.raises(RuntimeError, match="already attempted"):
        upload(media, state, Opener())


def test_preflight_and_rights_reject_without_any_remote_write(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    state = tmp_path / "attempts"
    opener = Opener()
    with pytest.raises(ValueError, match="preflight"):
        PrivateUpload(str(state), opener=opener).upload_once(
            str(media), access_token="token", channel_id=CHANNEL, title="Sample",
            rights_confirmed=True, preflight=lambda path: False)
    with pytest.raises(ValueError, match="rights"):
        PrivateUpload(str(state), opener=opener).upload_once(
            str(media), access_token="token", channel_id=CHANNEL, title="Sample",
            rights_confirmed=False, preflight=lambda path: True)
    assert not opener.calls
    assert not state.exists()


def test_wrong_authenticated_channel_blocks_before_any_post(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    state = tmp_path / "attempts"
    opener = Opener(channel="UC-other")
    with pytest.raises(RuntimeError, match="channel mismatch"):
        upload(media, state, opener)
    assert [r.get_method() for r in opener.calls] == ["GET"]
    assert not state.exists()


def test_invalid_session_url_blocks_before_media_put(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    state = tmp_path / "attempts"
    opener = Opener(session_url="https://www.googleapis.com.evil.tld/upload/youtube/v3/videos?upload_id=x")
    with pytest.raises(RuntimeError, match="outcome unknown"):
        upload(media, state, opener)
    assert [r.get_method() for r in opener.calls] == ["GET", "POST"]
    assert marker(state)["state"] == "REMOTE_UNKNOWN"


def test_remote_readback_public_fails_closed_but_retains_video_id(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    state = tmp_path / "attempts"
    with pytest.raises(RuntimeError, match="outcome unknown"):
        upload(media, state, Opener(readback_private=False))
    assert marker(state)["state"] == "REMOTE_UNKNOWN"
    assert marker(state)["video_id"] == VIDEO_ID


def test_file_mutation_after_session_prevents_put_and_leaves_lock(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"test media")
    state = tmp_path / "attempts"
    opener = Opener(mutate_after_post=lambda: media.write_bytes(b"DIFFERENT CONTENT"))
    with pytest.raises(RuntimeError, match="outcome unknown"):
        upload(media, state, opener)
    assert [r.get_method() for r in opener.calls] == ["GET", "POST"]
    assert marker(state)["state"] == "REMOTE_UNKNOWN"


def test_bad_308_range_refuses_retry_or_new_session(tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"x" * (256 * 1024 + 1))
    state = tmp_path / "attempts"
    opener = Opener(bad_ack=True)
    client = PrivateUpload(str(state), opener=opener)
    client.CHUNK_BYTES = 256 * 1024
    with pytest.raises(RuntimeError, match="outcome unknown"):
        client.upload_once(str(media), access_token="token", channel_id=CHANNEL,
                           title="Test", rights_confirmed=True, preflight=lambda path: True)
    assert [r.get_method() for r in opener.calls] == ["GET", "POST", "PUT"]
    assert marker(state)["state"] == "REMOTE_UNKNOWN"



def test_explicit_read_only_reconciliation_survives_restart(tmp_path):
    media = tmp_path / "original.mp4"
    media.write_bytes(b"licensed fixture")
    state = tmp_path / "attempts"
    with pytest.raises(RuntimeError, match="outcome unknown"):
        upload(media, state, Opener(readback_private=False))
    assert marker(state)["video_id"] == VIDEO_ID
    check_transport = Opener()
    result = PrivateUpload(str(state), opener=check_transport).reconcile_existing(
        str(media), access_token="fresh-token", channel_id=CHANNEL)
    assert result["state"] == "REMOTE_CONFIRMED_PRIVATE"
    assert marker(state)["state"] == "REMOTE_CONFIRMED_PRIVATE"
    assert [request.get_method() for request in check_transport.calls] == ["GET", "GET"]
    with pytest.raises(RuntimeError, match="already attempted"):
        upload(media, state, Opener())


def test_missing_video_id_is_unknown_and_no_new_remote_write(tmp_path):
    media = tmp_path / "original.mp4"
    media.write_bytes(b"licensed fixture")
    state = tmp_path / "attempts"
    with pytest.raises(RuntimeError, match="outcome unknown"):
        upload(media, state, Opener(fail_post=True))
    verifier = Opener()
    result = PrivateUpload(str(state), opener=verifier).reconcile_existing(
        str(media), access_token="fresh-token", channel_id=CHANNEL)
    assert result["state"] == "REMOTE_UNKNOWN"
    assert not verifier.calls
    assert marker(state)["video_id"] == ""


def test_changed_file_cannot_reconcile_another_upload(tmp_path):
    media = tmp_path / "original.mp4"
    media.write_bytes(b"licensed fixture")
    state = tmp_path / "attempts"
    upload(media, state, Opener())
    media.write_bytes(b"changed")
    verifier = Opener()
    with pytest.raises(ValueError, match="No previous upload attempt"):
        PrivateUpload(str(state), opener=verifier).reconcile_existing(
            str(media), access_token="fresh-token", channel_id=CHANNEL)
    assert not verifier.calls
