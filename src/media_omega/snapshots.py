from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
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
        observed = datetime.fromisoformat(observation.observed_at.replace("Z", "+00:00"))
        observed_key = observed.astimezone(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO snapshots(platform, content_id, observed_at, payload) VALUES (?, ?, ?, ?)",
                (observation.platform, observation.content_id, observed_key, payload),
            )
            return cursor.rowcount == 1

    def history(self, platform: str, content_id: str) -> list[ContentObservation]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT payload FROM snapshots WHERE platform=? AND content_id=? ORDER BY observed_at ASC",
                (platform, content_id),
            ).fetchall()
        result = [ContentObservation(**json.loads(row[0])) for row in rows]
        return sorted(result, key=lambda x: datetime.fromisoformat(x.observed_at.replace("Z", "+00:00")).astimezone(timezone.utc))

    def latest(self, platform: str = "youtube") -> list[ContentObservation]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT payload FROM snapshots WHERE platform=? ORDER BY content_id",
                (platform,),
            ).fetchall()
        latest_by_content = {}
        for row in rows:
            observation = ContentObservation(**json.loads(row[0]))
            observed = datetime.fromisoformat(observation.observed_at.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                raise ValueError("stored observed_at must be timezone-aware")
            observed_utc = observed.astimezone(timezone.utc)
            previous = latest_by_content.get(observation.content_id)
            if previous is None or observed_utc > previous[0]:
                latest_by_content[observation.content_id] = (observed_utc, observation)
        return [latest_by_content[key][1] for key in sorted(latest_by_content)]

    def count(self) -> int:
        with sqlite3.connect(self.path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])
