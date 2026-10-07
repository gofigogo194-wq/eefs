from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Protocol

from .discovery import DiscoveryItem
from .evidence import record_evidence
from .memory import DecisionJournal
from .observations import ContentObservation


class StatisticsTransport(Protocol):
    def video_statistics(self, video_ids: list[str]) -> dict[str, int]:
        ...


@dataclass(frozen=True)
class EnrichmentResult:
    requested: int
    enriched: int
    missing: int
    observation_ids: tuple[str, ...]
    mode: str = "read-only"


def enrich_statistics(
    items: list[DiscoveryItem],
    transport: StatisticsTransport,
    journal: DecisionJournal,
    creator_baselines: dict[str, float] | None = None,
    observed_at: str | None = None,
) -> tuple[list[ContentObservation], EnrichmentResult]:
    creator_baselines = creator_baselines or {}
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    unique: dict[str, DiscoveryItem] = {}
    for item in items:
        if item.platform != "youtube":
            continue
        unique.setdefault(item.content_id, item)

    ids = list(unique)
    stats: dict[str, int] = {}
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        stats.update(transport.video_statistics(batch))

    observations: list[ContentObservation] = []
    for video_id, item in unique.items():
        if video_id not in stats:
            continue
        baseline = max(float(creator_baselines.get(item.creator_id, 1.0)), 1.0)
        observation = ContentObservation(
            platform="youtube",
            content_id=video_id,
            creator_id=item.creator_id,
            published_at=item.published_at,
            observed_at=timestamp,
            views=int(stats[video_id]),
            creator_baseline_views=baseline,
            evidence_ref=f"api://youtube/videos/{video_id}@{timestamp}",
        )
        observation.validate()
        record_evidence(journal, "youtube_statistics.v1", observation)
        observations.append(observation)

    result = EnrichmentResult(
        requested=len(unique),
        enriched=len(observations),
        missing=len(unique) - len(observations),
        observation_ids=tuple(x.content_id for x in observations),
    )
    journal.append("STATISTICS_ENRICHMENT", asdict(result))
    return observations, result
