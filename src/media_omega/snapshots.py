from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .observations import ContentObservation


class SnapshotStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    platform TEXT NOT NULL,
                    content_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (platform, content_id, observed_at)
                )
            """)

    def append(self, observation: ContentObservation) -> bool:
        observation.validate()
        payload = json.dumps(asdict(observation), sort_keys=True)
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO snapshots(platform, content_id, observed_at, payload) VALUES (?, ?, ?, ?)",
                (observation.platform, observation.content_id, observation.observed_at, payload),
            )
            return cursor.rowcount == 1

    def history(self, platform: str, content_id: str) -> list[ContentObservation]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT payload FROM snapshots WHERE platform=? AND content_id=? ORDER BY observed_at ASC",
                (platform, content_id),
            ).fetchall()
        return [ContentObservation(**json.loads(row[0])) for row in rows]

    def latest(self, platform: str = "youtube") -> list[ContentObservation]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute("""
                SELECT s.payload FROM snapshots s
                JOIN (
                    SELECT platform, content_id, MAX(observed_at) AS observed_at
                    FROM snapshots WHERE platform=?
                    GROUP BY platform, content_id
                ) latest
                ON s.platform=latest.platform
                AND s.content_id=latest.content_id
                AND s.observed_at=latest.observed_at
                ORDER BY s.content_id
            """, (platform,)).fetchall()
        return [ContentObservation(**json.loads(row[0])) for row in rows]

    def count(self) -> int:
        with sqlite3.connect(self.path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])
