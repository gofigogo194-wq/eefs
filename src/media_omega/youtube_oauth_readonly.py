"""OAuth 2.0 PKCE authorization preparation for YouTube read-only access.

No listener, token exchange, disk persistence, or upload capability.
The browser authorization URL is generated locally; secrets stay in memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import base64
import secrets
from urllib.parse import urlencode


AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
UPLOAD_CONNECTION_SCOPE = READONLY_SCOPE + " " + UPLOAD_SCOPE


@dataclass(frozen=True)
class ReadOnlyOAuthRequest:
    authorization_url: str
    state: str
    code_verifier: str
    redirect_uri: str
    scope: str = READONLY_SCOPE


def prepare_readonly_authorization(client_id: str, redirect_uri: str) -> ReadOnlyOAuthRequest:
    """Prepare a read-only OAuth login; unchanged existing permission."""
    return _prepare_authorization(client_id, redirect_uri, READONLY_SCOPE)


def prepare_upload_authorization(client_id: str, redirect_uri: str) -> ReadOnlyOAuthRequest:
    """Prepare an opt-in upload-scoped OAuth login; NO token exchange or upload."""
    return _prepare_authorization(client_id, redirect_uri, UPLOAD_CONNECTION_SCOPE)


def _prepare_authorization(client_id: str, redirect_uri: str, scope: str) -> ReadOnlyOAuthRequest:
    if scope not in (READONLY_SCOPE, UPLOAD_CONNECTION_SCOPE):
        raise ValueError("unsupported OAuth scope")
    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("OAuth client ID required")
    # Loopback browser callback for a desktop app; never accept arbitrary
    # URLs or remote domains as the code receiver.
    if not isinstance(redirect_uri, str) or not (
        redirect_uri.startswith("http://127.0.0.1:")
        or redirect_uri.startswith("http://localhost:")
    ):
        raise ValueError("OAuth redirect must be loopback HTTP")
    from urllib.parse import urlsplit
    parts = urlsplit(redirect_uri)
    if parts.username or parts.password or not parts.port or parts.path not in ("", "/"):
        raise ValueError("invalid loopback redirect")
    if parts.hostname not in {"localhost", "127.0.0.1"} or parts.query or parts.fragment:
        raise ValueError("invalid loopback redirect")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    # An explicit reconnect can issue a new offline refresh token for persistence.
    # Applied to UPLOAD only; read-only auth keeps its previous behavior.
    if scope == UPLOAD_CONNECTION_SCOPE:
        params["prompt"] = "consent"
    return ReadOnlyOAuthRequest(AUTH_ENDPOINT + "?" + urlencode(params), state, verifier, redirect_uri, scope)


def validate_callback_state(expected: str, received: str) -> bool:
    if not isinstance(expected, str) or not isinstance(received, str) or not expected:
        return False
    return secrets.compare_digest(expected, received)
