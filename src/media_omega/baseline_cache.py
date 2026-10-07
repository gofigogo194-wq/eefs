from __future__ import annotations

from dataclasses import dataclass, field

from .baseline_collection import BaselineCollectionResult, collect_creator_baseline


@dataclass
class CreatorBaselineCache:
    """Run-scoped cache: one creator-history fetch per target exclusion key."""

    transport: object
    minimum_samples: int = 3
    _cache: dict[tuple[str, str | None], BaselineCollectionResult] = field(default_factory=dict)

    def get(self, creator_id: str, target_content_id: str | None = None) -> BaselineCollectionResult:
        key = (creator_id, target_content_id)
        if key not in self._cache:
            self._cache[key] = collect_creator_baseline(
                self.transport,
                creator_id,
                target_content_id=target_content_id,
                minimum_samples=self.minimum_samples,
            )
        return self._cache[key]

    @property
    def size(self) -> int:
        return len(self._cache)
