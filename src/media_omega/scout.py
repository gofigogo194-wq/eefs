from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class ScoutTopic:
    query: str
    prior_score: float = 0.5
    observations: int = 0
    successes: int = 0


@dataclass(frozen=True)
class ScoutDecision:
    queries: tuple[str, ...]
    explore_count: int
    exploit_count: int
    policy_version: str = "scout.v1"


@dataclass(frozen=True)
class ScoutPolicy:
    query_budget: int = 5
    exploration_fraction: float = 0.4

    def validate(self) -> None:
        if not 1 <= self.query_budget <= 20:
            raise ValueError("query_budget must be between 1 and 20")
        if not 0.0 <= self.exploration_fraction <= 1.0:
            raise ValueError("exploration_fraction must be between 0 and 1")


def _query_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _posterior(topic: ScoutTopic) -> float:
    if not topic.query.strip():
        raise ValueError("scout query is required")
    if not 0.0 <= topic.prior_score <= 1.0:
        raise ValueError("prior_score must be between 0 and 1")
    if topic.observations < 0 or topic.successes < 0 or topic.successes > topic.observations:
        raise ValueError("invalid scout history")
    empirical = (topic.successes + 1) / (topic.observations + 2)
    evidence_weight = min(topic.observations / 20.0, 1.0)
    return (1.0 - evidence_weight) * topic.prior_score + evidence_weight * empirical


def choose_queries(
    known_topics: list[ScoutTopic],
    exploration_queries: list[str],
    policy: ScoutPolicy | None = None,
) -> ScoutDecision:
    policy = policy or ScoutPolicy()
    policy.validate()
    budget = policy.query_budget
    explore_n = min(round(budget * policy.exploration_fraction), len(exploration_queries))
    exploit_n = budget - explore_n

    known_keys: set[str] = set()
    for topic in known_topics:
        _posterior(topic)
        key = _query_key(topic.query)
        if key in known_keys:
            raise ValueError("known scout queries must be unique")
        known_keys.add(key)

    ranked = sorted(
        known_topics,
        key=lambda topic: (-_posterior(topic), _query_key(topic.query)),
    )
    exploit = [topic.query for topic in ranked[:exploit_n]]

    # Deterministic ordering makes every decision reproducible for audit/tests.
    exploration: dict[str, str] = {}
    for value in exploration_queries:
        if not isinstance(value, str):
            raise ValueError("exploration queries must be strings")
        clean = " ".join(value.split())
        key = _query_key(clean)
        if key and key not in known_keys:
            exploration.setdefault(key, clean)
    unseen = sorted(
        exploration.values(),
        key=lambda q: sha256(_query_key(q).encode("utf-8")).hexdigest(),
    )
    explore = unseen[:explore_n]

    remaining = budget - len(exploit) - len(explore)
    if remaining > 0:
        extra = [topic.query for topic in ranked[exploit_n:] if topic.query not in exploit]
        exploit.extend(extra[:remaining])

    queries = tuple((exploit + explore)[:budget])
    return ScoutDecision(
        queries=queries,
        explore_count=len(explore),
        exploit_count=len(queries) - len(explore),
    )
