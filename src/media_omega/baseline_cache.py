from __future__ import annotations

from dataclasses import dataclass, field

from .baseline_collection import BaselineCollectionResult, collect_creator_baseline


@dataclass
class CreatorBaselineCache:
    """Run-scoped cache: one raw creator-history fetch, with target exclusion derived locally."""

    transport: object
    minimum_samples: int = 3
    _cache: dict[tuple[str, str | None], BaselineCollectionResult] = field(default_factory=dict)\n    _raw_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)\n    _raw_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    def get(self, creator_id: str, target_content_id: str | None = None) -> BaselineCollectionResult:
        key = (creator_id, target_content_id)
        if key in self._cache:
            return self._cache[key]
        if creator_id not in self._raw_ids:
            ids = tuple(self.transport.channel_recent_video_ids(creator_id))
            stats: dict[str, int] = {}
            for start in range(0, len(ids), 50):
                stats.update(self.transport.video_statistics(list(ids[start:start + 50])))
            self._raw_ids[creator_id] = ids
            self._raw_stats[creator_id] = stats
        ids = [x for x in self._raw_ids[creator_id] if x != target_content_id]
        stats = self._raw_stats[creator_id]
        values = [stats[x] for x in ids if x in stats]
        excluded = target_content_id is not None and target_content_id in self._raw_ids[creator_id]
        from .baseline import build_creator_baseline
        baseline = build_creator_baseline(creator_id, values) if len(values) >= self.minimum_samples else None
        self._cache[key] = BaselineCollectionResult(
            creator_id, len(ids), len(values), excluded, baseline,
            "READY" if baseline is not None else "INSUFFICIENT_HISTORY",
        )
        return self._cache[key]

    @property
    def size(self) -> int:
        return len(self._cache)
