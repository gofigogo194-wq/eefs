"""Minimal GET-only YouTube Data API client; no upload or OAuth flow.

An access token is supplied by the caller in memory. Do not journal or log it.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class YouTubeReadOnlyAPI:
    BASE_URL = "https://www.googleapis.com/youtube/v3/"
    ALLOWED_PATHS = frozenset({"channels", "videos"})

    def __init__(self, access_token: str, *, timeout: float = 10.0, opener=None):
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("access token required")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
            raise ValueError("invalid request timeout")
        self._token = access_token
        self._timeout = timeout
        self._opener = opener if opener is not None else build_opener(_NoRedirect())

    def _get(self, resource: str, query: dict) -> dict:
        if resource not in self.ALLOWED_PATHS:
            raise ValueError("read-only endpoint not allowed")
        url = self.BASE_URL + resource + "?" + urlencode(query)
        request = Request(
            url, headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/json",
            }, method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                data = response.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError("API response too large")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("YouTube read-only API request failed") from None
        try:
            result = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise RuntimeError("YouTube API returned invalid JSON") from None
        if not isinstance(result, dict):
            raise RuntimeError("YouTube API expected an object response")
        return result

    def get_authenticated_channel(self) -> dict:
        data = self._get("channels", {"part": "id", "mine": "true"})
        items = data.get("items")
        if not isinstance(items, list) or len(items) != 1:
            raise RuntimeError("expected exactly one authenticated channel")
        item = items[0]
        if not isinstance(item, dict):
            raise RuntimeError("invalid channel response")
        return {"id": item.get("id")}

    def get_video(self, video_id: str) -> dict | None:
        if not isinstance(video_id, str) or not video_id.strip():
            raise ValueError("video ID required")
        data = self._get("videos", {
            "part": "snippet,status", "id": video_id,
            "maxResults": 1,
        })
        items = data.get("items")
        if not isinstance(items, list) or len(items) > 1:
            raise RuntimeError("invalid video listing response")
        if not items:
            return None
        video = items[0]
        if not isinstance(video, dict) or not isinstance(video.get("snippet"), dict) or not isinstance(video.get("status"), dict):
            raise RuntimeError("invalid video metadata")
        return {
            "id": video.get("id"),
            "channel_id": video["snippet"].get("channelId"),
            "privacy_status": video["status"].get("privacyStatus"),
        }
