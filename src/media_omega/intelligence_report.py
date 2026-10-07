from __future__ import annotations

from dataclasses import asdict, dataclass

from .baseline_cache import CreatorBaselineCache
from .intelligence_pipeline import IntelligenceSignal, evaluate_content, rank_signals
from .memory import DecisionJournal
from .snapshots import SnapshotStore


@dataclass(frozen=True)
class IntelligenceReport:
    ready: tuple[IntelligenceSignal, ...]
    insufficient_snapshot_history: tuple[str, ...]
    insufficient_creator_history: tuple[str, ...]
    unreliable_interval: tuple[str, ...] = ()
    required_snapshots: int = 3


def analyze_intelligence(
    store: SnapshotStore,
    journal: DecisionJournal,
    transport,
) -> IntelligenceReport:
    cache = CreatorBaselineCache(transport)
    ready: list[IntelligenceSignal] = []
    short: list[str] = []
    no_creator_history: list[str] = []
    unreliable: list[str] = []

    for latest in store.latest("youtube"):
        history = store.history("youtube", latest.content_id)
        if len(history) < 3:
            short.append(latest.content_id)
            continue
        try:
            signal = evaluate_content(history, cache)
        except ValueError as exc:
            if "interval is too short" in str(exc):
                unreliable.append(latest.content_id)
                continue
            raise
        if signal.status != "READY":
            no_creator_history.append(latest.content_id)
            continue
        ready.append(signal)

    ranked = tuple(rank_signals(ready))
    report = IntelligenceReport(
        ranked,
        tuple(sorted(short)),
        tuple(sorted(no_creator_history)),
        tuple(sorted(unreliable)),
    )
    journal.append("INTELLIGENCE_REPORT", {
        "ready": [asdict(x) for x in report.ready],
        "insufficient_snapshot_history": list(report.insufficient_snapshot_history),
        "insufficient_creator_history": list(report.insufficient_creator_history),
        "unreliable_interval": list(report.unreliable_interval),
        "required_snapshots": report.required_snapshots,
        "creator_baseline_cache_entries": cache.size,
    })
    return report
