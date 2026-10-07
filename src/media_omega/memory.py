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


class DecisionJournal:
    def __init__(self, path: str | Path = "data/media_omega.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30.0)

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
            if "prev_hash" not in columns:
                db.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT")
            if "event_hash" not in columns:
                db.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")

            needs_backfill = db.execute(
                "SELECT 1 FROM events WHERE prev_hash IS NULL OR event_hash IS NULL LIMIT 1"
            ).fetchone() is not None
            if needs_backfill:
                db.execute("DROP TRIGGER IF EXISTS events_append_only_update")
                db.execute("DROP TRIGGER IF EXISTS events_append_only_delete")
                previous = _GENESIS_HASH
                rows = db.execute(
                    "SELECT id,created_at,event_type,payload_json,prev_hash,event_hash "
                    "FROM events ORDER BY id"
                ).fetchall()
                for row in rows:
                    event_id, created_at, event_type, payload_json, prev_hash, event_hash = row
                    expected = _hash_event(previous, created_at, event_type, payload_json)
                    if prev_hash is None or event_hash is None:
                        db.execute(
                            "UPDATE events SET prev_hash=?,event_hash=? WHERE id=?",
                            (previous, expected, event_id),
                        )
                        event_hash = expected
                    previous = str(event_hash)

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

    def append(self, event_type: str, payload: dict[str, Any]) -> int:
        if not event_type.strip():
            raise ValueError("event_type is required")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        created_at = utc_now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT event_hash FROM events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = str(row[0]) if row and row[0] else _GENESIS_HASH
            event_hash = _hash_event(prev_hash, created_at, event_type, body)
            cur = db.execute(
                "INSERT INTO events("
                "created_at,event_type,payload_json,prev_hash,event_hash"
                ") VALUES(?,?,?,?,?)",
                (created_at, event_type, body, prev_hash, event_hash),
            )
            return int(cur.lastrowid)

    def verify_chain(self) -> bool:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,created_at,event_type,payload_json,prev_hash,event_hash "
                "FROM events ORDER BY id"
            ).fetchall()
        previous = _GENESIS_HASH
        for _, created_at, event_type, payload_json, prev_hash, event_hash in rows:
            if prev_hash is None or event_hash is None:
                return False
            if prev_hash != previous:
                return False
            expected = _hash_event(previous, created_at, event_type, payload_json)
            if event_hash != expected:
                return False
            previous = event_hash
        return True

    def chain_head(self) -> str:
        with self._connect() as db:
            row = db.execute(
                "SELECT event_hash FROM events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return str(row[0]) if row and row[0] else _GENESIS_HASH

    def read_all(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,created_at,event_type,payload_json FROM events ORDER BY id"
            ).fetchall()
        return [
            {
                "id": row[0],
                "created_at": row[1],
                "event_type": row[2],
                "payload": json.loads(row[3]),
            }
            for row in rows
        ]
