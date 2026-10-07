from __future__ import annotations

from dataclasses import dataclass, field

from .baseline import build_creator_baseline, sample_at
from .baseline_collection import BaselineCollectionResult


@dataclass
class CreatorBaselineCache:
    """Run-scoped cache for live creator-history samples.

    Historical video views are age-normalized using the actual observation time
    returned by the transport, never a target video's older snapshot time.
    """

    transport: object
    minimum_samples: int = 3
    _raw_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _raw_details: dict[str, dict[str, dict[str, object]]] = field(default_factory=dict)
    _results: dict[tuple[str, str | None], BaselineCollectionResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")

    def _load(self, creator_id: str) -> None:
        if creator_id in self._raw_ids:
            return
        ids = tuple(self.transport.channel_recent_video_ids(creator_id))
        details: dict[str, dict[str, object]] = {}
        for start in range(0, len(ids), 50):
            batch = list(ids[start:start + 50])
            returned = self.transport.video_details(batch)
            details.update({key: value for key, value in returned.items() if key in batch})
        self._raw_ids[creator_id] = ids
        self._raw_details[creator_id] = details

    def get(
        self,
        creator_id: str,
        target_content_id: str | None = None,
    ) -> BaselineCollectionResult:
        if not creator_id.strip():
            raise ValueError("creator_id is required")
        key = (creator_id, target_content_id)
        if key in self._results:
            return self._results[key]

        self._load(creator_id)
        raw_ids = self._raw_ids[creator_id]
        selected = [x for x in raw_ids if x != target_content_id]
        details = self._raw_details[creator_id]
        samples = []
        source_refs: list[str] = []
        source_observed_at: list[str] = []

        for content_id in selected:
            detail = details.get(content_id)
            if detail is None:
                continue
            observed_at = str(detail["observed_at"])
            sample = sample_at(
                int(detail["views"]),
                str(detail["published_at"]),
                observed_at,
            )
            if sample is not None:
                samples.append(sample)
                source_refs.append(f"api://youtube/videos/{content_id}")
                source_observed_at.append(observed_at)

        excluded = target_content_id is not None and target_content_id in raw_ids
        baseline = (
            build_creator_baseline(creator_id, samples)
            if len(samples) >= self.minimum_samples
            else None
        )
        result = BaselineCollectionResult(
            creator_id,
            len(selected),
            len(samples),
            excluded,
            baseline,
            "READY" if baseline is not None else "INSUFFICIENT_HISTORY",
            tuple(source_refs),
            tuple(source_observed_at),
        )
        self._results[key] = result
        return result

    @property
    def size(self) -> int:
        return len(self._results)
