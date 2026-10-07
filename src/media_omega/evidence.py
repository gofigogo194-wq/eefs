from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from .memory import DecisionJournal


@dataclass(frozen=True)
class EvidenceReceipt:
    event_id: int
    evidence_type: str
    sha256: str
    evidence_ref: str


def canonical_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        payload = asdict(value)
    elif isinstance(value, dict):
        payload = dict(value)
    else:
        raise TypeError("evidence payload must be a dataclass or dict")
    # Fail early if evidence cannot be represented deterministically.
    json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return payload


def evidence_hash(value: Any) -> str:
    payload = canonical_payload(value)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def record_evidence(
    journal: DecisionJournal,
    evidence_type: str,
    value: Any,
) -> EvidenceReceipt:
    if not evidence_type.strip():
        raise ValueError("evidence_type is required")
    payload = canonical_payload(value)
    digest = evidence_hash(payload)
    evidence_ref = f"journal://evidence/{digest}"
    event_id = journal.append("EVIDENCE", {
        "evidence_type": evidence_type,
        "sha256": digest,
        "evidence_ref": evidence_ref,
        "payload": payload,
    })
    return EvidenceReceipt(
        event_id=event_id,
        evidence_type=evidence_type,
        sha256=digest,
        evidence_ref=evidence_ref,
    )


def evidence_ref_exists(journal: DecisionJournal, evidence_ref: str) -> bool:
    if not evidence_ref.startswith("journal://evidence/"):
        return False
    for event in journal.read_all():
        if event["event_type"] != "EVIDENCE":
            continue
        payload = event["payload"]
        if payload.get("evidence_ref") != evidence_ref:
            continue
        digest = payload.get("sha256")
        value = payload.get("payload")
        if not isinstance(digest, str) or not isinstance(value, dict):
            return False
        return digest == evidence_hash(value)
    return False
