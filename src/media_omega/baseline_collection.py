from __future__ import annotations

from dataclasses import dataclass

from .baseline import CreatorBaseline, build_creator_baseline, sample_at


@dataclass(frozen=True)
class BaselineCollectionResult:
    creator_id: str
    requested_ids: int
    returned_stats: int
    excluded_target: bool
    baseline: CreatorBaseline | None
    status: str
    source_refs: tuple[str, ...] = ()
    source_observed_at: tuple[str, ...] = ()


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

    ids = list(transport.channel_recent_video_ids(creator_id))
    excluded = False
    if target_content_id:
        before = len(ids)
        ids = [x for x in ids if x != target_content_id]
        excluded = len(ids) != before

    details: dict[str, dict[str, object]] = {}
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        returned = transport.video_details(batch)
        details.update({key: value for key, value in returned.items() if key in batch})

    samples = []
    source_refs: list[str] = []
    source_observed_at: list[str] = []
    for content_id in ids:
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

    if len(samples) < minimum_samples:
        return BaselineCollectionResult(
            creator_id,
            len(ids),
            len(samples),
            excluded,
            None,
            "INSUFFICIENT_HISTORY",
            tuple(source_refs),
            tuple(source_observed_at),
        )
    return BaselineCollectionResult(
        creator_id,
        len(ids),
        len(samples),
        excluded,
        build_creator_baseline(creator_id, samples),
        "READY",
        tuple(source_refs),
        tuple(source_observed_at),
    )
