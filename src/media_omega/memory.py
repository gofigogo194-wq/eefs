from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from .models import utc_now


class DecisionJournal:
    def __init__(self, path: str | Path = "data/media_omega.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )""")

    def append(self, event_type: str, payload: dict[str, Any]) -> int:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO events(created_at,event_type,payload_json) VALUES(?,?,?)",
                (utc_now(), event_type, body),
            )
            return int(cur.lastrowid)

    def read_all(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,created_at,event_type,payload_json FROM events ORDER BY id"
            ).fetchall()
        return [
            {"id": r[0], "created_at": r[1], "event_type": r[2], "payload": json.loads(r[3])}
            for r in rows
        ]
