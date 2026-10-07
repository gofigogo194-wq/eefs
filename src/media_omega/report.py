from __future__ import annotations

from dataclasses import asdict, dataclass

from .memory import DecisionJournal
from .ranking import RankedOpportunity, rank_opportunities
from .snapshots import SnapshotStore
from .timeseries import momentum


@dataclass(frozen=True)
class MomentumReportItem:
    content_id: str
    sample_count: int
    latest_velocity: float
    acceleration_ratio: float
    sustained_growth: bool


@dataclass(frozen=True)
class AnalysisReport:
    ready: tuple[MomentumReportItem, ...]
    insufficient_history: tuple[str, ...]
    unreliable_interval: tuple[str, ...] = ()
    required_snapshots: int = 3


def analyze_tracked(store: SnapshotStore, journal: DecisionJournal) -> AnalysisReport:
    ready: list[MomentumReportItem] = []
    insufficient: list[str] = []
    unreliable: list[str] = []
    for latest in store.latest("youtube"):
        history = store.history("youtube", latest.content_id)
        if len(history) < 3:
            insufficient.append(latest.content_id)
            continue
        try:
            signal = momentum(history)
        except ValueError as exc:
            if "interval is too short" in str(exc):
                unreliable.append(latest.content_id)
                continue
            raise
        ready.append(MomentumReportItem(
            content_id=latest.content_id,
            sample_count=signal.sample_count,
            latest_velocity=signal.latest_velocity,
            acceleration_ratio=signal.acceleration_ratio,
            sustained_growth=signal.sustained_growth,
        ))
    ready.sort(key=lambda x: (-x.acceleration_ratio, -x.latest_velocity, x.content_id))
    report = AnalysisReport(tuple(ready), tuple(sorted(insufficient)), tuple(sorted(unreliable)))
    journal.append("MOMENTUM_REPORT", {
        "ready": [asdict(x) for x in report.ready],
        "insufficient_history": list(report.insufficient_history),
        "unreliable_interval": list(report.unreliable_interval),
        "required_snapshots": report.required_snapshots,
    })
    return report
