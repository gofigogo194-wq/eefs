from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .observations import ContentObservation


class YouTubePayloadError(ValueError):
    pass


@dataclass
class YouTubeDataSource:
    """Adapter boundary for YouTube observations.

    The transport callable is injected deliberately: core logic never stores an API key
    and tests can prove normalization without network access.
    """

    transport: Callable[[], list[dict[str, Any]]]
    name: str = "youtube"

    def fetch(self) -> list[ContentObservation]:
        rows = self.transport()
        if not isinstance(rows, list):
            raise YouTubePayloadError("transport must return a list")
        observations: list[ContentObservation] = []
        for row in rows:
            try:
                content_id = str(row["content_id"])
                creator_id = str(row["creator_id"])
                published_at = str(row["published_at"])
                observed_at = str(row["observed_at"])
                views = int(row["views"])
                baseline = float(row["creator_baseline_views"])
                evidence_ref = str(row["evidence_ref"])
            except (KeyError, TypeError, ValueError) as exc:
                raise YouTubePayloadError("invalid YouTube observation payload") from exc

            item = ContentObservation(
                platform="youtube",
                content_id=content_id,
                creator_id=creator_id,
                published_at=published_at,
                observed_at=observed_at,
                views=views,
                creator_baseline_views=baseline,
                evidence_ref=evidence_ref,
            )
            item.validate()
            observations.append(item)
        return observations
