import json
from io import BytesIO

import pytest

from media_omega.youtube_connection import ReadOnlyConnectionSession
from media_omega.youtube_oauth_readonly import READONLY_SCOPE


class Reply:
    def __init__(self, payload):
        self.stream = BytesIO(json.dumps(payload).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        return self.stream.read(n)


class Opener:
    def __init__(self, payload, fail=False):
        self.payload = payload
        self.fail = fail
        self.calls = []
    def open(self, request, timeout):
        self.calls.append(request)
        if self.fail:
            raise TimeoutError("simulated network failure")
        return Reply(self.payload)


def setup(channel="UC-owner", *, token_fail=False, api_fail=False):
    token = Opener({"access_token": "secret", "expires_in": 3600, "scope": READONLY_SCOPE}, fail=token_fail)
    api = Opener({"items": [{"id": channel}]}, fail=api_fail)
    session = ReadOnlyConnectionSession(
        "client", "http://127.0.0.1:8765/", "UC-owner",
        token_opener=token, api_opener=api,
    )
    callback = session.authorization.redirect_uri + "?code=authorization-code&state=" + session.authorization.state
    return session, callback, token, api


def test_full_connection_flow_in_memory():
    session, callback, token, api = setup()
    assert "youtube.readonly" in session.authorization_url
    result = session.complete(callback)
    assert result.authorized is True
    assert result.channel_id == "UC-owner"
    assert result.mode == "READ_ONLY"
    assert result.published is False
    assert token.calls[0].get_method() == "POST"
    assert api.calls[0].get_method() == "GET"
    with pytest.raises(RuntimeError, match="consumed"):
        session.complete(callback)
    assert len(token.calls) == len(api.calls) == 1


@pytest.mark.parametrize("channel,token_fail,api_fail", [
    ("UC-wrong", False, False),
    ("UC-owner", True, False),
    ("UC-owner", False, True),
])
def test_connection_fails_closed_and_cannot_retry(channel, token_fail, api_fail):
    session, callback, token, api = setup(channel, token_fail=token_fail, api_fail=api_fail)
    with pytest.raises(RuntimeError):
        session.complete(callback)
    with pytest.raises(RuntimeError, match="consumed"):
        session.complete(callback)


def test_csrf_mismatch_is_terminal_without_network():
    session, callback, token, api = setup()
    with pytest.raises(ValueError, match="state"):
        session.complete(callback.replace(session.authorization.state, "attacker"))
    assert not token.calls and not api.calls
    with pytest.raises(RuntimeError, match="consumed"):
        session.complete(callback)
