from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class YouTubePayloadError(ValueError):
    """YouTube API payload violated the read-only transport contract."""


@dataclass(frozen=True)
class YouTubeReadOnlyConfig:
    api_key_env: str = "YOUTUBE_API_KEY"
    timeout_seconds: float = 10.0
    max_results: int = 25

    def validate(self) -> None:
        if not self.api_key_env.strip():
            raise ValueError("api_key_env is required")
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if not 1 <= self.max_results <= 50:
            raise ValueError("max_results must be between 1 and 50")

    def api_key(self) -> str:
        value = os.environ.get(self.api_key_env, "").strip()
        if not value:
            raise RuntimeError(f"missing required environment variable: {self.api_key_env}")
        return value


class YouTubeHTTPTransport:
    """Read-only YouTube Data API transport.

    It only performs GET requests. Credentials are read from the environment and
    are never returned in evidence references.
    """

    base_url = "https://www.googleapis.com/youtube/v3"

    def __init__(self, config: YouTubeReadOnlyConfig | None = None):
        self.config = config or YouTubeReadOnlyConfig()
        self.config.validate()

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = dict(params)
        api_key = self.config.api_key()
        url = f"{self.base_url}/{endpoint}?{urlencode(query)}"
        request = Request(url, method="GET", headers={
            "Accept": "application/json",
            "X-Goog-Api-Key": api_key,
        })
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise YouTubePayloadError(
                "YouTube API returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise YouTubePayloadError("YouTube API returned non-object JSON")
        return payload

    @staticmethod
    def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = payload.get("items", [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise YouTubePayloadError("YouTube API items must be a list of objects")
        return items

    @staticmethod
    def _required_text(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise YouTubePayloadError(f"{field} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _view_count(value: Any) -> int:
        try:
            views = int(value)
        except (TypeError, ValueError) as exc:
            raise YouTubePayloadError("viewCount must be an integer") from exc
        if views < 0:
            raise YouTubePayloadError("viewCount cannot be negative")
        return views

    def discover_videos(self, query: str) -> list[dict[str, str]]:
        if not query.strip():
            raise ValueError("query is required")
        payload = self._get_json("search", {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "date",
            "maxResults": self.config.max_results,
        })
        result: list[dict[str, str]] = []
        for item in self._items(payload):
            try:
                identity = item["id"]
                snippet = item["snippet"]
                if not isinstance(identity, dict) or not isinstance(snippet, dict):
                    raise YouTubePayloadError(
                        "invalid search.list discovery payload"
                    )
                video_id = self._required_text(
                    identity.get("videoId"),
                    "videoId",
                )
                creator_id = self._required_text(
                    snippet.get("channelId"),
                    "channelId",
                )
                title = self._required_text(snippet.get("title"), "title")
                published_at = self._required_text(
                    snippet.get("publishedAt"),
                    "publishedAt",
                )
                result.append({
                    "content_id": video_id,
                    "creator_id": creator_id,
                    "title": title,
                    "published_at": published_at,
                    "evidence_ref": f"api://youtube/search/{video_id}",
                })
            except YouTubePayloadError:
                raise
            except (KeyError, TypeError) as exc:
                raise YouTubePayloadError("invalid search.list discovery payload") from exc
        return result

    def video_statistics(self, video_ids: list[str]) -> dict[str, int]:
        clean = list(dict.fromkeys(x.strip() for x in video_ids if x.strip()))
        if not clean:
            return {}
        if len(clean) > 50:
            raise ValueError("YouTube videos.list supports at most 50 ids per request")
        payload = self._get_json("videos", {"part": "statistics", "id": ",".join(clean)})
        result: dict[str, int] = {}
        for item in self._items(payload):
            try:
                item_id = self._required_text(item.get("id"), "id")
                if item_id not in clean:
                    raise YouTubePayloadError("videos.list returned an unexpected id")
                if item_id in result:
                    raise YouTubePayloadError("videos.list returned a duplicate id")
                result[item_id] = self._view_count(item["statistics"]["viewCount"])
            except YouTubePayloadError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise YouTubePayloadError("invalid videos.list statistics payload") from exc
        return result

    def video_details(self, video_ids: list[str]) -> dict[str, dict[str, object]]:
        clean = list(dict.fromkeys(x.strip() for x in video_ids if x.strip()))
        if not clean:
            return {}
        if len(clean) > 50:
            raise ValueError("YouTube videos.list supports at most 50 ids per request")
        payload = self._get_json("videos", {"part": "snippet,statistics", "id": ",".join(clean)})
        observed_at = datetime.now(timezone.utc).isoformat()
        result: dict[str, dict[str, object]] = {}
        for item in self._items(payload):
            try:
                item_id = self._required_text(item.get("id"), "id")
                if item_id not in clean:
                    raise YouTubePayloadError("videos.list returned an unexpected id")
                if item_id in result:
                    raise YouTubePayloadError("videos.list returned a duplicate id")
                published_at = str(item["snippet"]["publishedAt"])
                published = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )
                if published.tzinfo is None:
                    raise YouTubePayloadError("publishedAt must be timezone-aware")
                result[item_id] = {
                    "views": self._view_count(item["statistics"]["viewCount"]),
                    "published_at": published_at,
                    "observed_at": observed_at,
                }
            except YouTubePayloadError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise YouTubePayloadError("invalid videos.list details payload") from exc
        return result

    def channel_recent_video_ids(self, channel_id: str) -> list[str]:
        if not channel_id.strip():
            raise ValueError("channel_id is required")
        payload = self._get_json("search", {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "maxResults": min(max(self.config.max_results, 1), 50),
        })
        ids: list[str] = []
        for item in self._items(payload):
            identity = item.get("id")
            if not isinstance(identity, dict):
                raise YouTubePayloadError(
                    "invalid search.list channel payload"
                )
            video_id = self._required_text(
                identity.get("videoId"),
                "videoId",
            )
            if video_id in ids:
                raise YouTubePayloadError(
                    "search.list returned a duplicate video id"
                )
            ids.append(video_id)
        return ids
