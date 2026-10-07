from media_omega.evaluation import evaluate_from_history
from media_omega.memory import DecisionJournal
from media_omega.observations import ContentObservation
from media_omega.snapshots import SnapshotStore


def obs(content, hour, views, baseline=1000):
    return ContentObservation(
        "youtube", content, "creator",
        "2026-10-07T00:00:00+00:00",
        f"2026-10-07T{hour:02d}:00:00+00:00",
        views, baseline, f"api://youtube/{content}/{hour}",
    )


def test_evaluation_defers_until_three_snapshots(tmp_path):
    store = SnapshotStore(tmp_path / "s.db")
    store.append(obs("target", 1, 100))
    store.append(obs("target", 2, 300))
    journal = DecisionJournal(tmp_path / "j.db")
    result = evaluate_from_history(store, "youtube", "target", [obs("peer", 2, 100)], journal)
    assert result.status == "INSUFFICIENT_HISTORY"
    assert result.candidate is None
    assert journal.read_all()[-1]["event_type"] == "EVALUATION_DEFERRED"


def test_evaluation_defers_without_peers(tmp_path):
    store = SnapshotStore(tmp_path / "s.db")
    for x in [obs("target", 1, 100), obs("target", 2, 300), obs("target", 3, 900)]:
        store.append(x)
    result = evaluate_from_history(
        store, "youtube", "target", [], DecisionJournal(tmp_path / "j.db")
    )
    assert result.status == "INSUFFICIENT_PEERS"


def test_persisted_history_becomes_auditable_candidate(tmp_path):
    store = SnapshotStore(tmp_path / "s.db")
    for x in [obs("target", 1, 100), obs("target", 2, 300), obs("target", 3, 900)]:
        store.append(x)
    peers = [obs(f"peer{i}", 3, 100 + i * 10) for i in range(5)]
    journal = DecisionJournal(tmp_path / "j.db")
    result = evaluate_from_history(store, "youtube", "target", peers, journal)
    assert result.status == "CANDIDATE"
    assert result.candidate is not None
    assert result.candidate.acceleration_ratio == 3.0
    assert result.candidate.evidence_count == 8
    assert journal.read_all()[-1]["event_type"] == "OPPORTUNITY_CANDIDATE"
