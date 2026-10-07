from __future__ import annotations

from dataclasses import dataclass

from .baseline import CreatorBaseline, build_creator_baseline


@dataclass(frozen=True)
class BaselineCollectionResult:
    creator_id: str
    requested_ids: int
    returned_stats: int
    excluded_target: bool
    baseline: CreatorBaseline | None
    status: str


def collect_creator_baseline(
    transport,
    creator_id: str,
    target_content_id: str | None = None,
    minimum_samples: int = 3,
) -> BaselineCollectionResult:
    if not creator_id.strip():
        raise ValueError("creator_id is required")
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be positive")
    ids = transport.channel_recent_video_ids(creator_id)
    excluded = False
    if target_content_id:
        before = len(ids)
        ids = [x for x in ids if x != target_content_id]
        excluded = len(ids) != before
    stats: dict[str, int] = {}
    for start in range(0, len(ids), 50):
        stats.update(transport.video_statistics(ids[start:start + 50]))
    values = [stats[x] for x in ids if x in stats]
    if len(values) < minimum_samples:
        return BaselineCollectionResult(
            creator_id, len(ids), len(values), excluded, None, "INSUFFICIENT_HISTORY"
        )
    return BaselineCollectionResult(
        creator_id,
        len(ids),
        len(values),
        excluded,
        build_creator_baseline(creator_id, values),
        "READY",
    )
