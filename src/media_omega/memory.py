from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import utc_now


_GENESIS_HASH = ""


def _hash_event(
    prev_hash: str,
    created_at: str,
    event_type: str,
    payload_json: str,
) -> str:
    encoded = json.dumps(
        {
            "prev_hash": prev_hash,
            "created_at": created_at,
            "event_type": event_type,
            "payload_json": payload_json,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_rows(rows: list[tuple]) -> bool:
    previous = _GENESIS_HASH
    for _, created_at, event_type, payload_json, prev_hash, event_hash in rows:
        if (
            not isinstance(created_at, str)
            or not created_at.strip()
            or not isinstance(event_type, str)
            or not event_type.strip()
            or not isinstance(payload_json, str)
            or not isinstance(prev_hash, str)
            or not isinstance(event_hash, str)
        ):
            return False
        try:
            decoded = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError):
            return False
        if not isinstance(decoded, dict):
            return False
        if prev_hash != previous:
            return False
        expected = _hash_event(previous, created_at, event_type, payload_json)
        if event_hash != expected:
            return False
        previous = event_hash
    return True


class DecisionJournal:
    def __init__(self, path: str | Path = "data/media_omega.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30.0)

    @staticmethod
    def _rows(db: sqlite3.Connection) -> list[tuple]:
        return db.execute(
            "SELECT id,created_at,event_type,payload_json,prev_hash,event_hash "
            "FROM events ORDER BY id"
        ).fetchall()

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                prev_hash TEXT,
                event_hash TEXT
            )""")
            columns = {
                row[1]
                for row in db.execute("PRAGMA table_info(events)").fetchall()
            }
            legacy_schema = "prev_hash" not in columns or "event_hash" not in columns

            db.execute("DROP TRIGGER IF EXISTS events_require_hash_insert")
            if "prev_hash" not in columns:
                db.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT")
            if "event_hash" not in columns:
                db.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")

            rows = self._rows(db)
            has_missing_hash = any(
                row[4] is None or row[5] is None
                for row in rows
            )
            if has_missing_hash:
                if not legacy_schema:
                    raise RuntimeError("decision journal contains unhashed events")
                db.execute("DROP TRIGGER IF EXISTS events_append_only_update")
                db.execute("DROP TRIGGER IF EXISTS events_append_only_delete")
                previous = _GENESIS_HASH
                for row in rows:
                    event_id, created_at, event_type, payload_json, _, _ = row
                    event_hash = _hash_event(
                        previous,
                        created_at,
                        event_type,
                        payload_json,
                    )
                    db.execute(
                        "UPDATE events SET prev_hash=?,event_hash=? WHERE id=?",
                        (previous, event_hash, event_id),
                    )
                    previous = event_hash

            rows = self._rows(db)
            if not _verify_rows(rows):
                raise RuntimeError("decision journal hash chain is invalid")

            db.execute("""CREATE TRIGGER IF NOT EXISTS events_append_only_update
                BEFORE UPDATE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'events are append-only');
                END
            """)
            db.execute("""CREATE TRIGGER IF NOT EXISTS events_append_only_delete
                BEFORE DELETE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'events are append-only');
                END
            """)
            db.execute("""CREATE TRIGGER IF NOT EXISTS events_require_hash_insert
                BEFORE INSERT ON events
                WHEN NEW.prev_hash IS NULL OR NEW.event_hash IS NULL
                BEGIN
                    SELECT RAISE(ABORT, 'hashed event fields are required');
                END
            """)

    @staticmethod
    def _append_verified(
        db: sqlite3.Connection,
        rows: list[tuple],
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        created_at = utc_now()
        prev_hash = str(rows[-1][5]) if rows else _GENESIS_HASH
        event_hash = _hash_event(prev_hash, created_at, event_type, body)
        cur = db.execute(
            "INSERT INTO events("
            "created_at,event_type,payload_json,prev_hash,event_hash"
            ") VALUES(?,?,?,?,?)",
            (created_at, event_type, body, prev_hash, event_hash),
        )
        return int(cur.lastrowid)

    def append(self, event_type: str, payload: dict[str, Any]) -> int:
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type is required")
        if not isinstance(payload, dict):
            raise TypeError("journal payload must be a dict")
        if event_type == "STATE_TRANSITION":
            raise ValueError("STATE_TRANSITION requires append_state_transition")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._rows(db)
            if not _verify_rows(rows):
                raise RuntimeError("decision journal hash chain is invalid")
            return self._append_verified(db, rows, event_type, payload)

    def append_publisher_dry_run_once(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Commit at most one identical offline publisher receipt per schedule.

        The uniqueness check and event insert share a BEGIN IMMEDIATE lock,
        including when separate processes use the same SQLite database.
        This is not a remote-upload idempotency guarantee.
        """
        if not isinstance(payload, dict):
            raise TypeError("publisher receipt must be an object")
        schedule_id = payload.get("schedule_id")
        entity_id = payload.get("entity_id")
        if (
            payload.get("version") != "publisher_adapter_dry_run.v1"
            or payload.get("mode") != "DRY_RUN"
            or payload.get("published") is not False
            or payload.get("remote_id") is not None
            or not isinstance(schedule_id, str)
            or not schedule_id.strip()
            or not isinstance(entity_id, str)
            or not entity_id.strip()
        ):
            raise ValueError("invalid offline publisher receipt")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._rows(db)
            if not _verify_rows(rows):
                raise RuntimeError("decision journal hash chain is invalid")
            # Require a real schedule transition for this entity.
            schedules = [
                json.loads(row[3]) for row in rows
                if row[2] == "STATE_TRANSITION"
                and json.loads(row[3]).get("entity_id") == entity_id
                and json.loads(row[3]).get("to_state") == "SCHEDULED"
            ]
            if len(schedules) != 1:
                raise ValueError("publisher receipt requires one admitted schedule")
            if schedules[0].get("evidence", {}).get("schedule_id") != schedule_id:
                raise ValueError("publisher schedule ID does not match admitted state")
            found = None
            for row in rows:
                if row[2] != "PUBLISHER_DRY_RUN":
                    continue
                existing = json.loads(row[3])
                if existing.get("schedule_id") != schedule_id:
                    continue
                if existing != payload:
                    raise RuntimeError("publisher dry-run receipt conflicts with prior schedule")
                if found is not None:
                    raise RuntimeError("duplicate historic publisher dry-run receipts")
                found = existing
            if found is not None:
                return found
            self._append_verified(db, rows, "PUBLISHER_DRY_RUN", payload)
            return dict(payload)

    def append_state_transition(
        self,
        payload: dict[str, Any],
        expected_from_state: str | None,
    ) -> int:
        if not isinstance(payload, dict):
            raise TypeError("state transition payload must be a dict")
        entity_id = payload.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("state transition entity_id is required")
        if payload.get("from_state") != expected_from_state:
            raise ValueError("transition payload from_state does not match expectation")

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = self._rows(db)
            if not _verify_rows(rows):
                raise RuntimeError("decision journal hash chain is invalid")

            current: str | None = None
            seen = False
            for row in rows:
                if row[2] != "STATE_TRANSITION":
                    continue
                try:
                    event_payload = json.loads(row[3])
                except json.JSONDecodeError as exc:
                    raise RuntimeError("invalid state transition payload") from exc
                if event_payload.get("entity_id") != entity_id:
                    continue
                value = event_payload.get("to_state")
                if not isinstance(value, str):
                    raise RuntimeError("invalid state transition state")
                current = value
                seen = True

            actual = current if seen else None
            if actual != expected_from_state:
                raise RuntimeError(
                    "state changed concurrently: "
                    f"expected {expected_from_state!r}, found {actual!r}"
                )
            return self._append_verified(
                db,
                rows,
                "STATE_TRANSITION",
                payload,
            )

    def verify_chain(self) -> bool:
        with self._connect() as db:
            return _verify_rows(self._rows(db))

    def chain_head(self) -> str:
        with self._connect() as db:
            rows = self._rows(db)
        if not _verify_rows(rows):
            raise RuntimeError("decision journal hash chain is invalid")
        return str(rows[-1][5]) if rows else _GENESIS_HASH

    def read_all(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = self._rows(db)
        if not _verify_rows(rows):
            raise RuntimeError("decision journal hash chain is invalid")
        return [
            {
                "id": row[0],
                "created_at": row[1],
                "event_type": row[2],
                "payload": json.loads(row[3]),
            }
            for row in rows
        ]
