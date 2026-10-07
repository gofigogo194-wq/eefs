from __future__ import annotations

from dataclasses import dataclass

from .observations import ContentObservation


def normalize_query(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True)
class PeerCohortPolicy:
    max_age_ratio: float
    minimum_peers: int = 3

    def validate(self) -> None:
        if self.max_age_ratio < 1.0:
            raise ValueError("max_age_ratio must be at least 1")
        if self.minimum_peers < 1:
            raise ValueError("minimum_peers must be positive")


@dataclass(frozen=True)
class PeerCohort:
    candidate_content_id: str
    peer_content_ids: tuple[str, ...]
    discovery_query: str
    content_format: str
    status: str
    excluded_platform: int
    excluded_query: int
    excluded_format: int
    excluded_age: int
    version: str = "peer_cohort.v1"


def build_peer_cohort(
    candidate: ContentObservation,
    peers: list[ContentObservation],
    policy: PeerCohortPolicy,
) -> PeerCohort:
    policy.validate()
    candidate.validate()
    query = normalize_query(candidate.discovery_query)
    if not query:
        return PeerCohort(
            candidate.content_id,
            (),
            "",
            candidate.content_format,
            "INSUFFICIENT_QUERY_PROVENANCE",
            0,
            0,
            0,
            0,
        )

    candidate_age = candidate.age_hours
    candidate_format = candidate.content_format.strip().casefold()
    known_format = candidate_format not in ("", "unknown")
    selected: list[ContentObservation] = []
    excluded_platform = excluded_query = excluded_format = excluded_age = 0

    for peer in peers:
        if peer.content_id == candidate.content_id:
            continue
        peer.validate()
        if peer.platform != candidate.platform:
            excluded_platform += 1
            continue
        if normalize_query(peer.discovery_query) != query:
            excluded_query += 1
            continue
        if known_format and peer.content_format.strip().casefold() != candidate_format:
            excluded_format += 1
            continue
        peer_age = peer.age_hours
        age_ratio = max(candidate_age, peer_age) / min(candidate_age, peer_age)
        if age_ratio > policy.max_age_ratio:
            excluded_age += 1
            continue
        selected.append(peer)

    status = "READY" if len(selected) >= policy.minimum_peers else "INSUFFICIENT_PEERS"
    if status == "READY" and not known_format:
        status = "READY_PARTIAL_FORMAT_UNKNOWN"

    return PeerCohort(
        candidate_content_id=candidate.content_id,
        peer_content_ids=tuple(sorted(peer.content_id for peer in selected)),
        discovery_query=query,
        content_format=candidate.content_format,
        status=status,
        excluded_platform=excluded_platform,
        excluded_query=excluded_query,
        excluded_format=excluded_format,
        excluded_age=excluded_age,
    )
