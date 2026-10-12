import json
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

import pytest

from media_omega.youtube_oauth_readonly import READONLY_SCOPE, prepare_readonly_authorization
from media_omega.youtube_oauth_exchange import SingleUseTokenExchange, TOKEN_ENDPOINT


class Response:
    def __init__(self, payload):
        self.payload = BytesIO(json.dumps(payload).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, length):
        return self.payload.read(length)


class RecordingOpener:
    def __init__(self, payload=None, error=False):
        self.payload = payload or {
            "access_token": "fake-token", "expires_in": 3600,
            "scope": READONLY_SCOPE,
        }
        self.error = error
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise TimeoutError("simulated")
        return Response(self.payload)


def prepared():
    request = prepare_readonly_authorization("test-client", "http://127.0.0.1:8765/")
    url = "http://127.0.0.1:8765/?code=test-code&state=" + request.state
    return request, url


def test_exchange_is_pkce_scoped_single_use():
    request, callback = prepared()
    opener = RecordingOpener()
    exchange = SingleUseTokenExchange(request, "test-client", opener=opener)
    token = exchange.exchange_callback(callback)
    assert token.access_token == "fake-token"
    assert token.scope == READONLY_SCOPE
    request_obj, timeout = opener.calls[0]
    assert request_obj.get_method() == "POST"
    assert request_obj.full_url == TOKEN_ENDPOINT
    body = parse_qs(request_obj.data.decode())
    assert body["code_verifier"] == [request.code_verifier]
    assert body["grant_type"] == ["authorization_code"]
    assert body["client_id"] == ["test-client"]
    with pytest.raises(RuntimeError, match="already attempted"):
        exchange.exchange_callback(callback)


@pytest.mark.parametrize("suffix", [
    "?code=test-code&state=wrong",
    "?code=test-code",
    "?code=one&code=two&state=wrong",
    "?error=access_denied",
    "?code=&state=wrong",
])
def test_bad_callback_never_contacts_token_endpoint(suffix):
    request, _ = prepared()
    opener = RecordingOpener()
    exchange = SingleUseTokenExchange(request, "test-client", opener=opener)
    with pytest.raises(ValueError):
        exchange.exchange_callback(request.redirect_uri + suffix.lstrip("/"))
    assert opener.calls == []


def test_wrong_callback_host_fails_before_network():
    request, _ = prepared()
    opener = RecordingOpener()
    exchange = SingleUseTokenExchange(request, "test-client", opener=opener)
    with pytest.raises(ValueError, match="origin"):
        exchange.exchange_callback("http://attacker.example/?code=x&state=" + request.state)
    assert not opener.calls


def test_error_is_nonretryable():
    request, callback = prepared()
    exchange = SingleUseTokenExchange(request, "test-client", opener=RecordingOpener(error=True))
    with pytest.raises(RuntimeError, match="uncertain"):
        exchange.exchange_callback(callback)
    with pytest.raises(RuntimeError, match="already attempted"):
        exchange.exchange_callback(callback)


def test_broad_scope_and_incomplete_token_are_rejected():
    for payload in [
        {"access_token": "x", "expires_in": 3600, "scope": READONLY_SCOPE + " other"},
        {"access_token": "x", "expires_in": 3600},
        {"access_token": "x", "expires_in": -1, "scope": READONLY_SCOPE},
        {"expires_in": 3600, "scope": READONLY_SCOPE},
    ]:
        request, callback = prepared()
        exchange = SingleUseTokenExchange(request, "client", opener=RecordingOpener(payload=payload))
        with pytest.raises(RuntimeError):
            exchange.exchange_callback(callback)


def test_upload_exchange_accepts_exact_upload_scope_only():
    from media_omega.youtube_oauth_readonly import UPLOAD_SCOPE, UPLOAD_CONNECTION_SCOPE, prepare_upload_authorization
    request = prepare_upload_authorization("test-client", "http://127.0.0.1:8765/")
    callback = request.redirect_uri + "?code=abc&state=" + request.state
    response = RecordingOpener(payload={
        "access_token": "fake-upload-token", "expires_in": 3600, "scope": UPLOAD_CONNECTION_SCOPE,
    })
    token = SingleUseTokenExchange(request, "test-client", opener=response).exchange_callback(callback)
    assert set(token.scope.split()) == set(UPLOAD_CONNECTION_SCOPE.split())

    for scope in (READONLY_SCOPE, UPLOAD_SCOPE, "other"):
        request = prepare_upload_authorization("test-client", "http://127.0.0.1:8765/")
        callback = request.redirect_uri + "?code=abc&state=" + request.state
        with pytest.raises(RuntimeError, match="scope"):
            SingleUseTokenExchange(
                request, "test-client",
                opener=RecordingOpener(payload={
                    "access_token": "token", "expires_in": 3600, "scope": scope,
                })
            ).exchange_callback(callback)


def test_google_callback_with_trusted_issuer_succeeds():
    from urllib.parse import quote
    request, callback = prepared()
    callback += "&iss=" + quote("https://accounts.google.com", safe="")
    result = SingleUseTokenExchange(request, "test-client", opener=RecordingOpener()).exchange_callback(callback)
    assert result.access_token == "fake-token"


def test_google_callback_with_untrusted_issuer_fails_before_network():
    request, callback = prepared()
    opener = RecordingOpener()
    exchange = SingleUseTokenExchange(request, "test-client", opener=opener)
    with pytest.raises(ValueError, match="issuer"):
        exchange.exchange_callback(callback + "&iss=https%3A%2F%2Fevil.example")
    assert not opener.calls
