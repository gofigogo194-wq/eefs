"""Read-only OAuth callback/code exchange, with explicit single-use session.

No listener, token disk storage, upload scope, or video mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import parse_qs, urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

from .youtube_oauth_readonly import ReadOnlyOAuthRequest, READONLY_SCOPE, validate_callback_state


TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ReadOnlyToken:
    access_token: str
    expires_in: int
    scope: str


class SingleUseTokenExchange:
    """One attempt per authorization request, even after remote uncertainty."""

    def __init__(self, authorization: ReadOnlyOAuthRequest, client_id: str, *, opener=None):
        if not isinstance(authorization, ReadOnlyOAuthRequest):
            raise ValueError("OAuth authorization required")
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("OAuth client ID required")
        self.authorization = authorization
        self.client_id = client_id
        self.used = False
        self._opener = opener if opener is not None else build_opener(_RejectRedirect())

    def exchange_callback(self, callback_url: str) -> ReadOnlyToken:
        if self.used:
            raise RuntimeError("OAuth code exchange already attempted")
        # Mark consumed BEFORE any network request to prohibit retry after
        # uncertain transport outcomes.
        self.used = True
        if not isinstance(callback_url, str):
            raise ValueError("callback URL required")
        callback = urlsplit(callback_url)
        original = urlsplit(self.authorization.redirect_uri)
        if (callback.scheme, callback.hostname, callback.port, callback.path) != (
            original.scheme, original.hostname, original.port, original.path
        ) or callback.fragment or callback.username or callback.password:
            raise ValueError("OAuth callback origin mismatch")
        params = parse_qs(callback.query, keep_blank_values=True)
        if set(params) != {"code", "state"} or any(len(v) != 1 for v in params.values()):
            raise ValueError("invalid OAuth callback parameters")
        if not validate_callback_state(self.authorization.state, params["state"][0]):
            raise ValueError("OAuth state mismatch")
        code = params["code"][0]
        if not code or len(code) > 4096:
            raise ValueError("invalid OAuth authorization code")
        body = urlencode({
            "client_id": self.client_id,
            "code": code,
            "code_verifier": self.authorization.code_verifier,
            "redirect_uri": self.authorization.redirect_uri,
            "grant_type": "authorization_code",
        }).encode("ascii")
        request = Request(TOKEN_ENDPOINT, data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
        try:
            with self._opener.open(request, timeout=10) as response:
                raw = response.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024:
                    raise RuntimeError("OAuth token response too large")
        except (HTTPError, URLError, OSError, TimeoutError):
            raise RuntimeError("OAuth exchange failed or outcome uncertain") from None
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            raise RuntimeError("invalid OAuth token response") from None
        if not isinstance(payload, dict):
            raise RuntimeError("invalid OAuth token response")
        token, expires, scopes = (
            payload.get("access_token"), payload.get("expires_in"), payload.get("scope")
        )
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("OAuth access token missing")
        if isinstance(expires, bool) or not isinstance(expires, int) or not 0 < expires <= 86400:
            raise RuntimeError("invalid token lifetime")
        if not isinstance(scopes, str) or set(scopes.split()) != {READONLY_SCOPE}:
            raise RuntimeError("unexpected OAuth scopes")
        return ReadOnlyToken(token, expires, scopes)
