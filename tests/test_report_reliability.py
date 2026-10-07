from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation
from media_omega.report import analyze_tracked
from media_omega.snapshots import SnapshotStore


def test_report_classifies_too_short_intervals_instead_of_crashing(tmp_path):
    store = SnapshotStore(tmp_path / "snapshots.db")
    journal = DecisionJournal(tmp_path / "journal.db")
    for second, views in [(0, 100), (10, 120), (20, 150)]:
        store.append(ContentObservation(
            "youtube", "fast-sampled", "creator",
            "2026-10-07T00:00:00+00:00",
            f"2026-10-07T01:00:{second:02d}+00:00",
            views, 1000, f"fixture://{second}",
        ))
    report = analyze_tracked(store, journal)
    assert report.ready == ()
    assert report.unreliable_interval == ("fast-sampled",)
