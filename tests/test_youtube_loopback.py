"""Real localhost transport tests for Google OAuth dynamic-port callback.

Tests never send credentials to Google or run any YouTube write.
"""
from __future__ import annotations

import json
import socket
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

import pytest

from media_omega.youtube_loopback import LoopbackOAuthReceiver
from media_omega.youtube_connection import UploadConnectionSession
from media_omega.youtube_oauth_readonly import UPLOAD_CONNECTION_SCOPE


class _Response:
    def __init__(self, value):
        self.raw = BytesIO(json.dumps(value).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, count):
        return self.raw.read(count)


class _GoogleMock:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return _Response(self.payload)


def _active_pair():
    receiver = LoopbackOAuthReceiver()
    token_transport = _GoogleMock({
        "access_token": "non-real-test-access", "expires_in": 3600,
        "scope": UPLOAD_CONNECTION_SCOPE, "refresh_token": "non-real-refresh",
    })
    account_transport = _GoogleMock({"items": [{"id": "UC" + "a" * 22}]})
    session = UploadConnectionSession(
        "a" * 45 + ".apps.googleusercontent.com",
        receiver.redirect_uri,
        "UC" + "a" * 22,
        token_opener=token_transport, api_opener=account_transport,
        client_secret="not-real-secret",
    )
    receiver.start(session.authorization.state)
    return receiver, session, token_transport, account_transport


def _get(url):
    with urlopen(url, timeout=3) as response:
        return response.status, response.read(4096)


def test_real_callback_routes_to_media_not_another_local_project_and_completes_oauth():
    # Simulate GIFT HUNTER already occupying the old hardcoded port.
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            occupied.bind(("127.0.0.1", 8765))
            occupied.listen(1)
        except OSError:
            # Existing CI software may also own 8765; that's acceptable.
            pass
        receiver, session, tokens, channel = _active_pair()
        try:
            assert receiver.redirect_uri.startswith("http://127.0.0.1:")
            assert urlsplit(receiver.redirect_uri).port != 8765 or occupied.getsockname()[1] != 8765
            assert parse_qs(urlsplit(session.authorization_url).query)["redirect_uri"] == [receiver.redirect_uri]
            callback = receiver.redirect_uri + "?state=" + session.authorization.state + "&code=example-code"
            status, body = _get(callback)
            assert status == 200 and b"MEDIA OMEGA" in body
            received = receiver.take_callback()
            assert received == callback
            verified = session.complete(received)
            assert verified.authorized is True
            assert verified.mode == "UPLOAD"
            assert verified.channel_id == "UC" + "a" * 22
            assert verified.refresh_token == "non-real-refresh"
            assert len(tokens.requests) == len(channel.requests) == 1
            assert receiver.take_callback() is None
            assert b"example-code" not in body
        finally:
            receiver.close()
    finally:
        occupied.close()


def test_invalid_state_and_path_do_not_consume_the_oauth_session():
    receiver, session, tokens, channel = _active_pair()
    try:
        for suffix in (
            "?state=attacker&code=stolen",
            "?code=missing-state",
            "?state=" + session.authorization.state + "&code=some&state=duplicate",
        ):
            with pytest.raises(HTTPError) as info:
                _get(receiver.redirect_uri + suffix)
            assert info.value.code == 400
        with pytest.raises(HTTPError) as info:
            _get(receiver.redirect_uri + "wrong?state=" + session.authorization.state)
        assert info.value.code == 404
        assert receiver.take_callback() is None
        assert not tokens.requests and not channel.requests
        # A genuine response still succeeds after spurious loopback requests.
        status, _ = _get(receiver.redirect_uri + "?code=good&state=" + session.authorization.state)
        assert status == 200
        assert session.complete(receiver.take_callback()).authorized is True
    finally:
        receiver.close()


def test_single_use_callback_refuses_duplicate_google_redirect():
    receiver, session, *_ = _active_pair()
    try:
        url = receiver.redirect_uri + "?code=one&state=" + session.authorization.state
        assert _get(url)[0] == 200
        with pytest.raises(HTTPError) as error:
            _get(url)
        assert error.value.code == 409
        assert receiver.take_callback() == url
        assert receiver.take_callback() is None
    finally:
        receiver.close()


def test_receiver_fails_closed_if_not_started_and_rejects_bad_state():
    receiver = LoopbackOAuthReceiver()
    try:
        with pytest.raises(ValueError, match="invalid or repeated"):
            receiver.start("")
        with pytest.raises(HTTPError) as error:
            # socket bound but not yet accepting, so do not send before start.
            receiver.start("good")
            _get(receiver.redirect_uri + "?state=wrong&code=x")
        assert error.value.code == 400
        with pytest.raises(ValueError):
            receiver.start("again")
    finally:
        receiver.close()


def test_cancel_closes_port_and_does_not_leave_pending_callback():
    receiver, session, *_ = _active_pair()
    port = urlsplit(receiver.redirect_uri).port
    receiver.close()
    assert receiver.take_callback() is None
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(1)
        assert client.connect_ex(("127.0.0.1", port)) != 0


def test_exchange_rejects_wrong_local_origin_even_with_valid_state():
    receiver, session, token, _ = _active_pair()
    try:
        with pytest.raises(ValueError, match="origin"):
            session.complete("http://127.0.0.1:8765/?code=good&state=" +
                             session.authorization.state)
        assert len(token.requests) == 0
    finally:
        receiver.close()


def test_desktop_does_not_use_port_8765_or_manual_callback_dialog():
    from pathlib import Path
    from media_omega import desktop
    import inspect

    source = inspect.getsource(desktop.main)
    assert "http://127.0.0.1:8765/" not in source
    assert "simpledialog.askstring" not in source
    assert "receiver.redirect_uri" in source
    assert "receiver.take_callback()" in source
    assert "session.complete(callback)" in source
