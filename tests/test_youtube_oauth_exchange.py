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
