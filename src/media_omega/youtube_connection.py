"""One-shot in-memory YouTube read-only connection orchestrator.

No local listener or token persistence. Callback URL must be supplied by the
caller after browser consent; secrets must not be logged or stored.
"""
from __future__ import annotations

from dataclasses import dataclass

from .youtube_oauth_readonly import prepare_readonly_authorization
from .youtube_oauth_exchange import SingleUseTokenExchange
from .youtube_api_readonly import YouTubeReadOnlyAPI
from .youtube_readback import verify_account
from .youtube_upload_contract import UploadState


@dataclass(frozen=True)
class ChannelConnectionResult:
    channel_id: str
    authorized: bool
    mode: str = "READ_ONLY"
    published: bool = False


class ReadOnlyConnectionSession:
    def __init__(self, client_id: str, redirect_uri: str, expected_channel_id: str,
                 *, token_opener=None, api_opener=None):
        if not isinstance(expected_channel_id, str) or not expected_channel_id.strip():
            raise ValueError("expected channel ID required")
        self.authorization = prepare_readonly_authorization(client_id, redirect_uri)
        self._exchange = SingleUseTokenExchange(
            self.authorization, client_id, opener=token_opener,
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
            raise RuntimeError("read-only channel identity could not be confirmed")
        return ChannelConnectionResult(channel_id=checked.channel_id, authorized=True)
