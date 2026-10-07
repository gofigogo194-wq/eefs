from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .observations import ContentObservation


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_payload(observation: ContentObservation) -> dict:
    observation.validate()
    payload = asdict(observation)
    payload["published_at"] = _time(observation.published_at).isoformat()
    payload["observed_at"] = _time(observation.observed_at).isoformat()
    return payload


def _semantic_digest(payload: dict) -> str:
    semantic = dict(payload)
    semantic.pop("evidence_ref", None)
    encoded = json.dumps(
        semantic,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(encoded)


class SnapshotStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30.0)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    platform TEXT NOT NULL,
                    content_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    payload_sha256 TEXT,
                    semantic_sha256 TEXT,
                    PRIMARY KEY (platform, content_id, observed_at)
                )
            """)
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(snapshots)").fetchall()
            }
            legacy_schema = (
                "payload_sha256" not in columns
                or "semantic_sha256" not in columns
            )
            conn.execute("DROP TRIGGER IF EXISTS snapshots_require_hash_insert")
            if "payload_sha256" not in columns:
                conn.execute(
                    "ALTER TABLE snapshots ADD COLUMN payload_sha256 TEXT"
                )
            if "semantic_sha256" not in columns:
                conn.execute(
                    "ALTER TABLE snapshots ADD COLUMN semantic_sha256 TEXT"
                )

            rows = conn.execute(
                "SELECT platform,content_id,observed_at,payload,"
                "payload_sha256,semantic_sha256 FROM snapshots"
            ).fetchall()
            missing = any(row[4] is None or row[5] is None for row in rows)
            if missing:
                if not legacy_schema:
                    raise RuntimeError("snapshot store contains unhashed rows")
                conn.execute("DROP TRIGGER IF EXISTS snapshots_append_only_update")
                conn.execute("DROP TRIGGER IF EXISTS snapshots_append_only_delete")
                for platform, content_id, observed_at, payload, _, _ in rows:
                    parsed = self._validate_payload_identity(
                        platform,
                        content_id,
                        observed_at,
                        payload,
                    )
                    conn.execute(
                        "UPDATE snapshots SET payload_sha256=?,semantic_sha256=? "
                        "WHERE platform=? AND content_id=? AND observed_at=?",
                        (
                            _sha256_text(payload),
                            _semantic_digest(parsed),
                            platform,
                            content_id,
                            observed_at,
                        ),
                    )

            self._verify_all(conn)

            conn.execute("""CREATE TRIGGER IF NOT EXISTS snapshots_append_only_update
                BEFORE UPDATE ON snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'snapshots are append-only');
                END
            """)
            conn.execute("""CREATE TRIGGER IF NOT EXISTS snapshots_append_only_delete
                BEFORE DELETE ON snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'snapshots are append-only');
                END
            """)
            conn.execute("""CREATE TRIGGER IF NOT EXISTS snapshots_require_hash_insert
                BEFORE INSERT ON snapshots
                WHEN NEW.payload_sha256 IS NULL OR NEW.semantic_sha256 IS NULL
                BEGIN
                    SELECT RAISE(ABORT, 'snapshot hash fields are required');
                END
            """)

    @staticmethod
    def _validate_payload_identity(
        platform: str,
        content_id: str,
        observed_at: str,
        payload_text: str,
    ) -> dict:
        try:
            payload = json.loads(payload_text)
            if not isinstance(payload, dict):
                raise ValueError("snapshot payload must be an object")
            observation = ContentObservation(**payload)
            observation.validate()
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("invalid snapshot payload") from exc

        if observation.platform != platform or observation.content_id != content_id:
            raise RuntimeError("snapshot payload identity mismatch")
        if _time(observation.observed_at).isoformat() != observed_at:
            raise RuntimeError("snapshot observed_at identity mismatch")
        canonical = _canonical_payload(observation)
        return canonical

    def _decode_row(self, row: tuple) -> ContentObservation:
        platform, content_id, observed_at, payload_text, payload_hash, semantic_hash = row
        if not isinstance(payload_hash, str) or not isinstance(semantic_hash, str):
            raise RuntimeError("snapshot row is missing integrity hashes")
        if _sha256_text(payload_text) != payload_hash:
            raise RuntimeError("snapshot payload hash mismatch")
        canonical = self._validate_payload_identity(
            platform,
            content_id,
            observed_at,
            payload_text,
        )
        if _semantic_digest(canonical) != semantic_hash:
            raise RuntimeError("snapshot semantic hash mismatch")
        return ContentObservation(**canonical)

    def _verify_all(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT platform,content_id,observed_at,payload,"
            "payload_sha256,semantic_sha256 FROM snapshots "
            "ORDER BY platform,content_id,observed_at"
        ).fetchall()
        for row in rows:
            self._decode_row(row)

    def verify_integrity(self) -> bool:
        try:
            with self._connect() as conn:
                self._verify_all(conn)
            return True
        except RuntimeError:
            return False

    def append(self, observation: ContentObservation) -> bool:
        canonical = _canonical_payload(observation)
        payload = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
        )
        observed_key = canonical["observed_at"]
        payload_hash = _sha256_text(payload)
        semantic_hash = _semantic_digest(canonical)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT platform,content_id,observed_at,payload,"
                "payload_sha256,semantic_sha256 FROM snapshots "
                "WHERE platform=? AND content_id=? AND observed_at=?",
                (observation.platform, observation.content_id, observed_key),
            ).fetchone()
            if existing is not None:
                # Idempotence is allowed only after the persisted row itself
                # passes integrity verification. A tampered row must never be
                # hidden behind a matching stored semantic hash.
                self._decode_row(existing)
                existing_semantic_hash = existing[5]
                if existing_semantic_hash == semantic_hash:
                    return False
                raise RuntimeError(
                    "snapshot identity conflict for same content and observation time"
                )

            conn.execute(
                "INSERT INTO snapshots("
                "platform,content_id,observed_at,payload,payload_sha256,semantic_sha256"
                ") VALUES (?,?,?,?,?,?)",
                (
                    observation.platform,
                    observation.content_id,
                    observed_key,
                    payload,
                    payload_hash,
                    semantic_hash,
                ),
            )
            return True

    def history(self, platform: str, content_id: str) -> list[ContentObservation]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT platform,content_id,observed_at,payload,"
                "payload_sha256,semantic_sha256 FROM snapshots "
                "WHERE platform=? AND content_id=? ORDER BY observed_at ASC",
                (platform, content_id),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def latest(self, platform: str = "youtube") -> list[ContentObservation]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT platform,content_id,observed_at,payload,"
                "payload_sha256,semantic_sha256 FROM snapshots "
                "WHERE platform=? ORDER BY content_id,observed_at",
                (platform,),
            ).fetchall()

        latest_by_content: dict[str, tuple[datetime, ContentObservation]] = {}
        for row in rows:
            observation = self._decode_row(row)
            observed_utc = _time(observation.observed_at)
            previous = latest_by_content.get(observation.content_id)
            if previous is None or observed_utc > previous[0]:
                latest_by_content[observation.content_id] = (
                    observed_utc,
                    observation,
                )
        return [
            latest_by_content[key][1]
            for key in sorted(latest_by_content)
        ]

    def count(self) -> int:
        with self._connect() as conn:
            self._verify_all(conn)
            return int(
                conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            )
