from __future__ import annotations

from dataclasses import asdict, dataclass

from .discovery import DiscoveryItem, DiscoveryPolicy, select_candidates
from .enrichment import enrich_statistics
from .memory import DecisionJournal
from .scout import ScoutPolicy, ScoutTopic, choose_queries
from .snapshots import SnapshotStore


@dataclass(frozen=True)
class ReadOnlyCycleResult:
    queries: tuple[str, ...]
    discovered: int
    selected: int
    observations: int
    new_snapshots: int
    mode: str = "read-only"


def run_readonly_cycle(
    transport,
    journal: DecisionJournal,
    snapshots: SnapshotStore,
    known_topics: list[ScoutTopic],
    exploration_queries: list[str],
    scout_policy: ScoutPolicy | None = None,
    discovery_policy: DiscoveryPolicy | None = None,
) -> ReadOnlyCycleResult:
    decision = choose_queries(known_topics, exploration_queries, scout_policy)
    journal.append("SCOUT_DECISION", asdict(decision))
    discovered: list[DiscoveryItem] = []
    for query in decision.queries:
        rows = transport.discover_videos(query)
        journal.append("DISCOVERY_QUERY", {"query": query, "result_count": len(rows), "mode": "read-only"})
        discovered.extend(
            DiscoveryItem(
                platform="youtube",
                content_id=row["content_id"],
                creator_id=row["creator_id"],
                title=row["title"],
                published_at=row["published_at"],
                evidence_ref=row["evidence_ref"],
            )
            for row in rows
        )
    selected = select_candidates(discovered, discovery_policy)
    observations, _ = enrich_statistics(selected, transport, journal)
    inserted = sum(1 for observation in observations if snapshots.append(observation))
    result = ReadOnlyCycleResult(
        queries=decision.queries,
        discovered=len(discovered),
        selected=len(selected),
        observations=len(observations),
        new_snapshots=inserted,
    )
    journal.append("READONLY_CYCLE_RESULT", asdict(result))
    return result
