"""In-memory YouTube account verification, initial consent and token refresh.

Persistent credentials are handled only by the Windows DPAPI profile boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from .youtube_oauth_readonly import prepare_readonly_authorization, prepare_upload_authorization
from .youtube_oauth_exchange import SingleUseTokenExchange, refresh_upload_token
from .youtube_api_readonly import YouTubeReadOnlyAPI
from .youtube_readback import verify_account
from .youtube_upload_contract import UploadState


@dataclass(frozen=True)
class ChannelConnectionResult:
    channel_id: str
    authorized: bool
    mode: str = "READ_ONLY"
    published: bool = False
    access_token: str = field(default="", repr=False, compare=False)
    refresh_token: str = field(default="", repr=False, compare=False)
    expires_at: float = field(default=0.0, repr=False, compare=False)


class ReadOnlyConnectionSession:
    def __init__(self, client_id: str, redirect_uri: str, expected_channel_id: str,
                 *, token_opener=None, api_opener=None, _mode="READ_ONLY", client_secret=""):
        if not isinstance(expected_channel_id, str) or not expected_channel_id.strip():
            raise ValueError("expected channel ID required")
        if _mode not in ("READ_ONLY", "UPLOAD"):
            raise ValueError("invalid connection mode")
        self._mode = _mode
        prepare = prepare_upload_authorization if _mode == "UPLOAD" else prepare_readonly_authorization
        self.authorization = prepare(client_id, redirect_uri)
        self._exchange = SingleUseTokenExchange(
            self.authorization, client_id, opener=token_opener, client_secret=client_secret,
        )
        self._expected = expected_channel_id
        self._api_opener = api_opener
        self._finished = False

    @property
    def authorization_url(self) -> str:
        return self.authorization.authorization_url

    def complete(self, callback_url: str) -> ChannelConnectionResult:
        if self._finished:
            raise RuntimeError("OAuth connection attempt already consumed")
        self._finished = True
        token = self._exchange.exchange_callback(callback_url)
        api = YouTubeReadOnlyAPI(token.access_token, opener=self._api_opener)
        checked = verify_account(api, self._expected)
        if checked.state is not UploadState.NOT_STARTED or checked.channel_id != self._expected:
            raise RuntimeError("channel verification failed: " + checked.reason)
        return ChannelConnectionResult(channel_id=checked.channel_id, authorized=True,
                                       mode=self._mode, access_token=token.access_token,
                                       refresh_token=token.refresh_token,
                                       expires_at=time() + token.expires_in)


class UploadConnectionSession(ReadOnlyConnectionSession):
    """One-shot upload-scoped account verification. Never performs an upload."""

    def __init__(self, client_id: str, redirect_uri: str, expected_channel_id: str,
                 *, token_opener=None, api_opener=None, client_secret=""):
        super().__init__(client_id, redirect_uri, expected_channel_id,
                         token_opener=token_opener, api_opener=api_opener, _mode="UPLOAD",
                         client_secret=client_secret)



def renew_saved_upload_connection(client_id: str, client_secret: str, channel_id: str,
                                  refresh_token: str, *, token_opener=None,
                                  api_opener=None) -> ChannelConnectionResult:
    """Only claim restored authorization after fresh authenticated channel read."""
    if not isinstance(channel_id, str) or not channel_id.strip():
        raise ValueError("saved channel ID required")
    refreshed = refresh_upload_token(
        client_id, client_secret, refresh_token, opener=token_opener,
    )
    account = YouTubeReadOnlyAPI(refreshed.access_token, opener=api_opener)
    check = verify_account(account, channel_id)
    if check.state is not UploadState.NOT_STARTED or check.channel_id != channel_id:
        raise RuntimeError("saved YouTube channel verification failed")
    return ChannelConnectionResult(
        channel_id=check.channel_id, authorized=True, mode="UPLOAD",
        access_token=refreshed.access_token,
        refresh_token=refreshed.refresh_token or refresh_token,
        expires_at=time() + refreshed.expires_in,
    )
