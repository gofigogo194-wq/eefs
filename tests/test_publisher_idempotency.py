from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from media_omega.memory import DecisionJournal


def receipt(schedule="schedule-abc"):
    return {
        "version": "publisher_adapter_dry_run.v1",
        "entity_id": "youtube:one",
        "schedule_id": schedule,
        "published": False,
        "remote_id": None,
        "mode": "DRY_RUN",
    }


def test_atomic_replay_and_restart_does_not_duplicate(tmp_path):
    path = tmp_path / "journal.db"
    one = DecisionJournal(path)
    expected = receipt()
    assert one.append_publisher_dry_run_once(expected) == expected
    second = DecisionJournal(path)
    assert second.append_publisher_dry_run_once(expected) == expected
    assert len([e for e in second.read_all() if e["event_type"] == "PUBLISHER_DRY_RUN"]) == 1
    assert second.verify_chain()


def test_concurrent_writers_one_receipt(tmp_path):
    path = tmp_path / "journal.db"
    DecisionJournal(path)
    def invoke(_):
        return DecisionJournal(path).append_publisher_dry_run_once(receipt())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(invoke, range(20)))
    assert all(result == receipt() for result in results)
    journal = DecisionJournal(path)
    assert len([e for e in journal.read_all() if e["event_type"] == "PUBLISHER_DRY_RUN"]) == 1
    assert journal.verify_chain()


def test_conflicting_replay_fails_closed(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.append_publisher_dry_run_once(receipt())
    other = {**receipt(), "entity_id": "youtube:different"}
    with pytest.raises(RuntimeError, match="conflicts"):
        journal.append_publisher_dry_run_once(other)
    assert len([e for e in journal.read_all() if e["event_type"] == "PUBLISHER_DRY_RUN"]) == 1


def test_invalid_success_or_remote_claim_blocked(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    for payload in [
        {**receipt(), "published": True},
        {**receipt(), "remote_id": "remote"},
        {**receipt(), "mode": "LIVE"},
        {**receipt(), "schedule_id": ""},
    ]:
        with pytest.raises(ValueError, match="invalid"):
            journal.append_publisher_dry_run_once(payload)
    assert not any(e["event_type"] == "PUBLISHER_DRY_RUN" for e in journal.read_all())


def test_corrupted_journal_blocks_receipt(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.append_publisher_dry_run_once(receipt())
    with sqlite3.connect(journal.path) as conn:
        conn.execute("DROP TRIGGER events_append_only_update")
        conn.execute("UPDATE events SET payload_json='{}' WHERE event_type='PUBLISHER_DRY_RUN'")
    with pytest.raises(RuntimeError, match="hash chain"):
        journal.append_publisher_dry_run_once(receipt())
