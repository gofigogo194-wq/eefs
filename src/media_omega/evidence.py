from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from .memory import DecisionJournal


def canonical_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError("evidence payload must be a dataclass or dict")


def evidence_hash(value: Any) -> str:
    payload = canonical_payload(value)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def record_evidence(journal: DecisionJournal, evidence_type: str, value: Any) -> int:
    payload = canonical_payload(value)
    return journal.append("EVIDENCE", {
        "evidence_type": evidence_type,
        "sha256": evidence_hash(payload),
        "payload": payload,
    })
