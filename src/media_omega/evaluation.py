from __future__ import annotations

from dataclasses import dataclass

from .intelligence import OpportunityCandidate, build_candidate
from .memory import DecisionJournal
from .observations import ContentObservation
from .snapshots import SnapshotStore


@dataclass(frozen=True)
class EvaluationResult:
    content_id: str
    status: str
    history_count: int
    peer_count: int
    candidate: OpportunityCandidate | None = None


def evaluate_from_history(
    store: SnapshotStore,
    platform: str,
    content_id: str,
    peers: list[ContentObservation],
    journal: DecisionJournal,
    minimum_history: int = 3,
) -> EvaluationResult:
    if minimum_history < 3:
        raise ValueError("minimum_history cannot be below momentum requirement")
    history = store.history(platform, content_id)
    if len(history) < minimum_history:
        result = EvaluationResult(content_id, "INSUFFICIENT_HISTORY", len(history), len(peers))
        journal.append("EVALUATION_DEFERRED", {
            "content_id": content_id,
            "reason": result.status,
            "history_count": len(history),
            "required": minimum_history,
        })
        return result
    if not peers:
        result = EvaluationResult(content_id, "INSUFFICIENT_PEERS", len(history), 0)
        journal.append("EVALUATION_DEFERRED", {
            "content_id": content_id,
            "reason": result.status,
            "peer_count": 0,
        })
        return result

    candidate = build_candidate(history, peers, journal)
    return EvaluationResult(
        content_id=content_id,
        status="CANDIDATE",
        history_count=len(history),
        peer_count=len(peers),
        candidate=candidate,
    )
