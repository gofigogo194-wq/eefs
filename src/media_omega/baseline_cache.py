from __future__ import annotations

from dataclasses import dataclass, field

from .baseline import build_creator_baseline
from .baseline_collection import BaselineCollectionResult


@dataclass
class CreatorBaselineCache:
    """Run-scoped cache: fetch creator history once, then exclude targets locally."""

    transport: object
    minimum_samples: int = 3
    _raw_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _raw_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    _results: dict[tuple[str, str | None], BaselineCollectionResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")

    def _load(self, creator_id: str) -> None:
        if creator_id in self._raw_ids:
            return
        ids = tuple(self.transport.channel_recent_video_ids(creator_id))
        stats: dict[str, int] = {}
        for start in range(0, len(ids), 50):
            stats.update(self.transport.video_statistics(list(ids[start:start + 50])))
        self._raw_ids[creator_id] = ids
        self._raw_stats[creator_id] = stats

    def get(self, creator_id: str, target_content_id: str | None = None) -> BaselineCollectionResult:
        if not creator_id.strip():
            raise ValueError("creator_id is required")
        key = (creator_id, target_content_id)
        if key in self._results:
            return self._results[key]
        self._load(creator_id)
        raw_ids = self._raw_ids[creator_id]
        selected = [x for x in raw_ids if x != target_content_id]
        stats = self._raw_stats[creator_id]
        values = [stats[x] for x in selected if x in stats]
        excluded = target_content_id is not None and target_content_id in raw_ids
        baseline = build_creator_baseline(creator_id, values) if len(values) >= self.minimum_samples else None
        result = BaselineCollectionResult(
            creator_id, len(selected), len(values), excluded, baseline,
            "READY" if baseline is not None else "INSUFFICIENT_HISTORY",
        )
        self._results[key] = result
        return result

    @property
    def size(self) -> int:
        return len(self._results)
