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

    def __init__(self, access_token: str = "", *, api_key: str = "", timeout: float = 10.0, opener=None):
        if not isinstance(access_token, str) or not isinstance(api_key, str):
            raise ValueError("invalid API credential")
        if not access_token.strip() and not api_key.strip():
            raise ValueError("YouTube API key or access token required")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
            raise ValueError("invalid request timeout")
        self._token = access_token.strip()
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._opener = opener if opener is not None else build_opener(_NoRedirect())

    def _get(self, resource: str, query: dict) -> dict:
        if resource not in self.ALLOWED_PATHS:
            raise ValueError("read-only endpoint not allowed")
        if not self._token and resource == "channels":
            raise ValueError("authenticated channel read requires an OAuth token")
        if not self._token and not self._api_key:
            raise ValueError("YouTube credential required")
        parameters = dict(query)
        # API keys are only for public most-popular charts; not account reads.
        if not self._token:
            if resource != "videos" or parameters.get("chart") != "mostPopular":
                raise ValueError("API key mode allows public popular videos only")
            parameters["key"] = self._api_key
        url = self.BASE_URL + resource + "?" + urlencode(parameters)
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        request = Request(url, headers=headers, method="GET")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                data = response.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError("API response too large")
        except (HTTPError, URLError, TimeoutError, OSError):
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

    def get_popular_videos(self, *, region_code: str = "US", max_results: int = 20) -> list[dict]:
        """Get YouTube's published mostPopular chart, not reuse permissions."""
        if not isinstance(region_code, str) or len(region_code) != 2 or not region_code.isascii() or not region_code.isalpha():
            raise ValueError("two-letter region code required")
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 50:
            raise ValueError("max_results must be between 1 and 50")
        data = self._get("videos", {
            "part": "snippet,statistics,status",
            "chart": "mostPopular",
            "regionCode": region_code.upper(),
            "maxResults": max_results,
        })
        items = data.get("items")
        if not isinstance(items, list):
            raise RuntimeError("invalid popular videos response")
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet")
            if not isinstance(snippet, dict):
                continue
            video_id = item.get("id")
            if not isinstance(video_id, str) or not video_id:
                continue
            counts = item.get("statistics", {})
            if not isinstance(counts, dict):
                counts = {}
            try:
                views = int(counts.get("viewCount", 0))
            except (ValueError, TypeError):
                views = 0
            result.append({
                "video_id": video_id,
                "url": "https://www.youtube.com/watch?v=" + video_id,
                "title": str(snippet.get("title", "")),
                "channel_id": str(snippet.get("channelId", "")),
                "views": max(0, views),
                "reuse_permission": "NOT_VERIFIED",
            })
        return result
