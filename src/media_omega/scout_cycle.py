from __future__ import annotations

from dataclasses import asdict, dataclass

from .discovery import DiscoveryItem, DiscoveryPolicy, select_candidates
from .memory import DecisionJournal
from .scout import ScoutDecision, ScoutPolicy, ScoutTopic, choose_queries


@dataclass(frozen=True)
class ScoutCycleResult:
    queries: tuple[str, ...]
    discovered_count: int
    selected_count: int
    selected_ids: tuple[str, ...]
    mode: str = "read-only"


class ReadOnlyDiscoveryTransport:
    def discover_videos(self, query: str) -> list[dict[str, str]]:
        raise NotImplementedError


def run_scout_cycle(
    transport: ReadOnlyDiscoveryTransport,
    journal: DecisionJournal,
    known_topics: list[ScoutTopic],
    exploration_queries: list[str],
    scout_policy: ScoutPolicy | None = None,
    discovery_policy: DiscoveryPolicy | None = None,
) -> ScoutCycleResult:
    decision = choose_queries(known_topics, exploration_queries, scout_policy)
    journal.append("SCOUT_DECISION", asdict(decision))

    discovered: list[DiscoveryItem] = []
    for query in decision.queries:
        rows = transport.discover_videos(query)
        journal.append("DISCOVERY_QUERY", {
            "query": query,
            "result_count": len(rows),
            "mode": "read-only",
        })
        for row in rows:
            discovered.append(DiscoveryItem(
                platform="youtube",
                content_id=row["content_id"],
                creator_id=row["creator_id"],
                title=row["title"],
                published_at=row["published_at"],
                evidence_ref=row["evidence_ref"],
                discovery_query=query,
                content_format="unknown",
            ))

    selected = select_candidates(discovered, discovery_policy)
    result = ScoutCycleResult(
        queries=decision.queries,
        discovered_count=len(discovered),
        selected_count=len(selected),
        selected_ids=tuple(item.content_id for item in selected),
    )
    journal.append("SCOUT_CYCLE_RESULT", asdict(result))
    return result
