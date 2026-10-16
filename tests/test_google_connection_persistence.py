"""Persistent OAuth connection regression checks, including native Windows DPAPI."""
import json
import os
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs
from urllib.error import HTTPError

import pytest

from media_omega.windows_connection_store import WindowsConnectionStore, WindowsDPAPI
from media_omega.youtube_connection import renew_saved_upload_connection
from media_omega.youtube_oauth_exchange import refresh_upload_token, TOKEN_ENDPOINT
from media_omega.youtube_oauth_readonly import (
    prepare_upload_authorization, UPLOAD_CONNECTION_SCOPE,
)


class FakeProtector:
    def protect(self, value):
        return b"ENCRYPTED:" + bytes(a ^ 0x5A for a in value)

    def unprotect(self, value):
        if not value.startswith(b"ENCRYPTED:"):
            raise RuntimeError("invalid ciphertext")
        return bytes(a ^ 0x5A for a in value[len(b"ENCRYPTED:"):])


def profile():
    return {
        "client_id": "test-client", "client_secret": "client-secret-keep-private",
        "channel_id": "UC-owner", "api_key": "api-key-keep-private",
        "refresh_token": "refresh-keep-private",
    }


def test_saved_connection_survives_new_installs_and_contains_no_plaintext(tmp_path):
    path = tmp_path / "LOCALAPPDATA" / "MEDIA_OMEGA" / "youtube_connection.v1.dpapi"
    first = WindowsConnectionStore(path=path, protector=FakeProtector())
    first.save(profile())
    raw = path.read_bytes()
    assert b"refresh-keep-private" not in raw
    assert b"client-secret-keep-private" not in raw
    assert b"api-key-keep-private" not in raw
    assert b"UC-owner" not in raw
    second = WindowsConnectionStore(path=path, protector=FakeProtector())
    assert second.load() == profile()
    assert not list(path.parent.glob("*.tmp"))
    second.forget()
    assert second.load() is None


def test_corrupted_connection_is_fail_closed_not_auto_overwritten(tmp_path):
    path = tmp_path / "google.dpapi"
    store = WindowsConnectionStore(path=path, protector=FakeProtector())
    store.save(profile())
    bad = b"corrupted-ciphertext"
    path.write_bytes(bad)
    with pytest.raises(RuntimeError, match="not changed"):
        store.load()
    assert path.read_bytes() == bad


@pytest.mark.parametrize("bad", [
    {"client_id": "x", "refresh_token": "token", "channel_id": ""},
    {"client_id": 7}, {"access_token": "should-not-store"},
    {"client_secret": object()},
])
def test_invalid_or_unbound_credentials_never_persist(tmp_path, bad):
    store = WindowsConnectionStore(path=tmp_path / "secret.dpapi", protector=FakeProtector())
    with pytest.raises(ValueError):
        store.save(bad)
    assert not store.path.exists()


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is only available on Windows")
def test_real_windows_dpapi_roundtrip_is_user_scoped(tmp_path):
    dpapi = WindowsDPAPI()
    clear = b"test-google-refresh-" + os.urandom(18)
    encrypted = dpapi.protect(clear)
    assert encrypted != clear
    assert dpapi.unprotect(encrypted) == clear
    store = WindowsConnectionStore(path=tmp_path / "google.dpapi")
    store.save(profile())
    assert b"refresh-keep-private" not in store.path.read_bytes()
    assert WindowsConnectionStore(path=store.path).load() == profile()


class Response:
    def __init__(self, value):
        self.raw = BytesIO(json.dumps(value).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        return self.raw.read(n)


class TokenOpener:
    def __init__(self, payload=None, error=False):
        self.payload = payload or {
            "access_token": "new-upload-access",
            "expires_in": 3600,
            "scope": UPLOAD_CONNECTION_SCOPE,
        }
        self.error = error
        self.calls = []

    def open(self, req, timeout):
        self.calls.append(req)
        if self.error:
            raise HTTPError(req.full_url, 400, "bad token", {},
                            BytesIO(b'{"error_description":"sensitive credential"}'))
        return Response(self.payload)


class ChannelOpener:
    def __init__(self, channel="UC-owner"):
        self.channel = channel
        self.calls = []

    def open(self, req, timeout):
        self.calls.append(req)
        return Response({"items": [{"id": self.channel}]})


def test_upload_authorization_explicitly_requests_new_offline_grant():
    request = prepare_upload_authorization("client", "http://127.0.0.1:8765/")
    assert parse_qs(request.authorization_url.split("?", 1)[1])["prompt"] == ["consent"]
    assert parse_qs(request.authorization_url.split("?", 1)[1])["access_type"] == ["offline"]


def test_refresh_uses_only_google_token_endpoint_and_validates_scope():
    opener = TokenOpener()
    result = refresh_upload_token("client", "secret", "refresh-secret", opener=opener)
    assert result.access_token == "new-upload-access"
    assert result.refresh_token == ""
    req = opener.calls[0]
    assert req.full_url == TOKEN_ENDPOINT
    assert req.get_method() == "POST"
    data = parse_qs(req.data.decode())
    assert data["grant_type"] == ["refresh_token"]
    assert data["refresh_token"] == ["refresh-secret"]
    assert data["client_secret"] == ["secret"]
    assert "refresh-secret" not in repr(result)


def test_refresh_rejects_wrong_scope_and_hides_raw_google_errors():
    for scopes in ("https://www.googleapis.com/auth/youtube.readonly", "evil"):
        opener = TokenOpener(payload={"access_token": "a", "expires_in": 3600, "scope": scopes})
        with pytest.raises(RuntimeError, match="scope"):
            refresh_upload_token("client", "secret", "refresh", opener=opener)
    with pytest.raises(RuntimeError, match="reauthorization") as info:
        refresh_upload_token("client", "secret", "refresh", opener=TokenOpener(error=True))
    assert "sensitive credential" not in str(info.value)


def test_restored_connection_requires_same_authenticated_channel():
    token = TokenOpener()
    account_api = ChannelOpener(channel="UC-owner")
    connected = renew_saved_upload_connection(
        "client", "secret", "UC-owner", "refresh-old",
        token_opener=token, api_opener=account_api,
    )
    assert connected.authorized
    assert connected.mode == "UPLOAD"
    assert connected.channel_id == "UC-owner"
    assert connected.refresh_token == "refresh-old"
    assert connected.expires_at > 0
    assert [r.get_method() for r in account_api.calls] == ["GET"]
    with pytest.raises(RuntimeError, match="verification failed"):
        renew_saved_upload_connection(
            "client", "secret", "UC-owner", "refresh-old",
            token_opener=TokenOpener(), api_opener=ChannelOpener("UC-foreign"),
        )


def test_new_refresh_token_rotation_does_not_use_stale_grant():
    token = TokenOpener({
        "access_token": "new-upload-access",
        "expires_in": 1200,
        "scope": UPLOAD_CONNECTION_SCOPE,
        "refresh_token": "rotated-token",
    })
    account = renew_saved_upload_connection(
        "client", "secret", "UC-owner", "old-token",
        token_opener=token, api_opener=ChannelOpener(),
    )
    assert account.refresh_token == "rotated-token"
