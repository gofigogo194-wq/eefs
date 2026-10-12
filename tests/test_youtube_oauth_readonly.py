from urllib.parse import parse_qs, urlsplit

import pytest

from media_omega.youtube_oauth_readonly import (
    READONLY_SCOPE, prepare_readonly_authorization, validate_callback_state,
)


def test_pkce_authorization_is_readonly_and_unique():
    first = prepare_readonly_authorization("client.apps.googleusercontent.com", "http://127.0.0.1:8765/")
    second = prepare_readonly_authorization("client.apps.googleusercontent.com", "http://127.0.0.1:8765/")
    data = parse_qs(urlsplit(first.authorization_url).query)
    assert data["scope"] == [READONLY_SCOPE]
    assert data["response_type"] == ["code"]
    assert data["code_challenge_method"] == ["S256"]
    assert data["state"] == [first.state]
    assert "code_verifier" not in data
    assert first.code_verifier != second.code_verifier
    assert first.state != second.state
    assert validate_callback_state(first.state, first.state)
    assert not validate_callback_state(first.state, second.state)


@pytest.mark.parametrize("url", [
    "https://attacker.example/callback",
    "http://127.0.0.1.evil.example:8000/",
    "http://user:pass@localhost:8123/",
    "http://localhost:8123/callback",
    "http://localhost/",
    "http://localhost:8123/?leak=1",
    "file:///token",
])
def test_pkce_rejects_nonloopback_or_unsafe_redirect(url):
    with pytest.raises(ValueError):
        prepare_readonly_authorization("client", url)


def test_missing_client_and_blank_state_fail_closed():
    with pytest.raises(ValueError):
        prepare_readonly_authorization("", "http://localhost:8000/")
    assert not validate_callback_state("", "")


def test_upload_pkce_is_explicit_and_separate_from_readonly():
    from media_omega.youtube_oauth_readonly import UPLOAD_CONNECTION_SCOPE, prepare_upload_authorization
    request = prepare_upload_authorization("client", "http://127.0.0.1:8765/")
    params = parse_qs(urlsplit(request.authorization_url).query)
    assert set(params["scope"][0].split()) == set(UPLOAD_CONNECTION_SCOPE.split())
    assert params["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in params
    assert params["state"] == [request.state]
    readonly = prepare_readonly_authorization("client", "http://127.0.0.1:8765/")
    assert parse_qs(urlsplit(readonly.authorization_url).query)["scope"] == [READONLY_SCOPE]


def test_upload_oauth_keeps_loopback_and_client_validations():
    from media_omega.youtube_oauth_readonly import prepare_upload_authorization
    with pytest.raises(ValueError):
        prepare_upload_authorization("client", "https://malicious.example/callback")
    with pytest.raises(ValueError):
        prepare_upload_authorization("", "http://127.0.0.1:8765/")
