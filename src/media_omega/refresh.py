from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .memory import DecisionJournal
from .observations import ContentObservation
from .snapshots import SnapshotStore


@dataclass(frozen=True)
class RefreshResult:
    tracked: int
    returned: int
    new_snapshots: int
    missing: int
    mode: str = "read-only"


def refresh_tracked(
    store: SnapshotStore,
    transport,
    journal: DecisionJournal,
    observed_at: str | None = None,
) -> RefreshResult:
    tracked = store.latest("youtube")
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    ids = [x.content_id for x in tracked]
    stats: dict[str, int] = {}
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        returned = transport.video_statistics(batch)
        stats.update({key: value for key, value in returned.items() if key in batch})

    inserted = 0
    for previous in tracked:
        if previous.content_id not in stats:
            continue
        current = ContentObservation(
            platform=previous.platform,
            content_id=previous.content_id,
            creator_id=previous.creator_id,
            published_at=previous.published_at,
            observed_at=timestamp,
            views=int(stats[previous.content_id]),
            creator_baseline_views=previous.creator_baseline_views,
            evidence_ref=f"api://youtube/videos/{previous.content_id}@{timestamp}",
        )
        if store.append(current):
            inserted += 1

    result = RefreshResult(
        tracked=len(ids),
        returned=len(stats),
        new_snapshots=inserted,
        missing=len(ids) - len(stats),
    )
    journal.append("TRACKED_REFRESH", result.__dict__)
    return result
