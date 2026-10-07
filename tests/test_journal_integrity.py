import json
import sqlite3

import pytest

from media_omega.memory import DecisionJournal, _hash_event


def test_journal_builds_verifiable_hash_chain(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    assert journal.verify_chain() is True
    assert journal.chain_head() == ""

    journal.append("A", {"x": 1})
    first_head = journal.chain_head()
    assert len(first_head) == 64
    assert journal.verify_chain() is True

    journal.append("B", {"y": 2})
    assert journal.chain_head() != first_head
    assert journal.verify_chain() is True


def test_database_blocks_update_and_delete_of_events(tmp_path):
    path = tmp_path / "journal.db"
    journal = DecisionJournal(path)
    journal.append("A", {"x": 1})

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute("UPDATE events SET event_type='MUTATED' WHERE id=1")

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute("DELETE FROM events WHERE id=1")

    assert journal.verify_chain() is True


def test_legacy_journal_is_migrated_without_losing_events(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )""")
        db.execute(
            "INSERT INTO events(created_at,event_type,payload_json) VALUES(?,?,?)",
            ("2026-10-07T00:00:00+00:00", "LEGACY", json.dumps({"x": 1})),
        )

    journal = DecisionJournal(path)
    assert [x["event_type"] for x in journal.read_all()] == ["LEGACY"]
    assert journal.verify_chain() is True
    assert len(journal.chain_head()) == 64


def test_hash_chain_detects_payload_tamper_when_guards_are_bypassed(tmp_path):
    path = tmp_path / "journal.db"
    journal = DecisionJournal(path)
    journal.append("A", {"x": 1})
    journal.append("B", {"y": 2})
    assert journal.verify_chain() is True

    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER events_append_only_update")
        db.execute("UPDATE events SET payload_json=? WHERE id=1", ('{"x":999}',))

    assert journal.verify_chain() is False


def test_direct_unhashed_insert_is_blocked(tmp_path):
    path = tmp_path / "journal.db"
    DecisionJournal(path)
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="hashed event fields"):
            db.execute(
                "INSERT INTO events(created_at,event_type,payload_json) VALUES(?,?,?)",
                ("2026-10-07T00:00:00+00:00", "BYPASS", "{}"),
            )


def test_append_refuses_to_extend_a_tampered_chain(tmp_path):
    path = tmp_path / "journal.db"
    journal = DecisionJournal(path)
    journal.append("A", {"x": 1})
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER events_append_only_update")
        db.execute("UPDATE events SET payload_json=? WHERE id=1", ('{"x":2}',))
    with pytest.raises(RuntimeError, match="hash chain"):
        journal.append("B", {"y": 1})


def test_read_all_fails_closed_after_tamper(tmp_path):
    path = tmp_path / "journal.db"
    journal = DecisionJournal(path)
    journal.append("A", {"x": 1})
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER events_append_only_update")
        db.execute("UPDATE events SET payload_json=? WHERE id=1", ('{"x":2}',))
    with pytest.raises(RuntimeError, match="hash chain"):
        journal.read_all()


def state_payload(entity, from_state, to_state):
    return {
        "entity_id": entity,
        "from_state": from_state,
        "to_state": to_state,
        "reason": "",
        "evidence": {},
        "contract_version": "state_transition.v1",
    }


def test_generic_append_cannot_bypass_state_transition_cas(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    with pytest.raises(ValueError, match="append_state_transition"):
        journal.append(
            "STATE_TRANSITION",
            state_payload("x", None, "IDEA"),
        )


def test_state_compare_and_append_rejects_duplicate_registration(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.append_state_transition(
        state_payload("x", None, "IDEA"),
        expected_from_state=None,
    )
    with pytest.raises(RuntimeError, match="changed concurrently"):
        journal.append_state_transition(
            state_payload("x", None, "IDEA"),
            expected_from_state=None,
        )


def test_state_compare_and_append_rejects_stale_expected_state(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    journal.append_state_transition(
        state_payload("x", None, "IDEA"),
        expected_from_state=None,
    )
    journal.append_state_transition(
        state_payload("x", "IDEA", "EVIDENCE_COLLECTED"),
        expected_from_state="IDEA",
    )
    with pytest.raises(RuntimeError, match="changed concurrently"):
        journal.append_state_transition(
            state_payload("x", "IDEA", "BLOCKED"),
            expected_from_state="IDEA",
        )


def test_hash_valid_but_non_object_event_payload_fails_integrity(tmp_path):
    path = tmp_path / "journal.db"
    journal = DecisionJournal(path)
    journal.append("A", {"x": 1})

    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER events_append_only_update")
        db.execute("DROP TRIGGER events_append_only_delete")
        db.execute("DROP TRIGGER events_require_hash_insert")
        rows = journal._rows(db)
        journal._append_verified(db, rows, "FORGED", {"temporary": True})
        forged_id = db.execute("SELECT MAX(id) FROM events").fetchone()[0]
        row = db.execute(
            "SELECT created_at,event_type,prev_hash FROM events WHERE id=?",
            (forged_id,),
        ).fetchone()
        created_at, event_type, prev_hash = row
        payload_json = "[]"
        event_hash = _hash_event(
            prev_hash,
            created_at,
            event_type,
            payload_json,
        )
        db.execute(
            "UPDATE events SET payload_json=?,event_hash=? WHERE id=?",
            (payload_json, event_hash, forged_id),
        )

    assert journal.verify_chain() is False
    with pytest.raises(RuntimeError, match="hash chain"):
        journal.read_all()
