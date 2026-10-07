from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from .memory import DecisionJournal


_RECEIPT_VERSION = "evidence_receipt.v2"


@dataclass(frozen=True)
class EvidenceReceipt:
    event_id: int
    evidence_type: str
    sha256: str
    evidence_ref: str
    version: str = _RECEIPT_VERSION


@dataclass(frozen=True)
class EvidenceRecord:
    receipt: EvidenceReceipt
    payload: dict[str, Any]


def canonical_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        payload = asdict(value)
    elif isinstance(value, dict):
        payload = dict(value)
    else:
        raise TypeError("evidence payload must be a dataclass or dict")
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


def _typed_digest(evidence_type: str, payload: dict[str, Any]) -> str:
    return evidence_hash({
        "evidence_type": evidence_type,
        "payload": payload,
        "receipt_version": _RECEIPT_VERSION,
    })


def record_evidence(
    journal: DecisionJournal,
    evidence_type: str,
    value: Any,
) -> EvidenceReceipt:
    if not evidence_type.strip():
        raise ValueError("evidence_type is required")
    payload = canonical_payload(value)
    digest = _typed_digest(evidence_type, payload)
    evidence_ref = f"journal://evidence/{digest}"
    event_id = journal.append("EVIDENCE", {
        "evidence_type": evidence_type,
        "sha256": digest,
        "evidence_ref": evidence_ref,
        "receipt_version": _RECEIPT_VERSION,
        "payload": payload,
    })
    return EvidenceReceipt(
        event_id=event_id,
        evidence_type=evidence_type,
        sha256=digest,
        evidence_ref=evidence_ref,
    )


def resolve_evidence(
    journal: DecisionJournal,
    evidence_ref: str,
) -> EvidenceRecord | None:
    if not evidence_ref.startswith("journal://evidence/"):
        return None
    matches: list[EvidenceRecord] = []
    for event in journal.read_all():
        if event["event_type"] != "EVIDENCE":
            continue
        body = event["payload"]
        if body.get("evidence_ref") != evidence_ref:
            continue
        evidence_type = body.get("evidence_type")
        digest = body.get("sha256")
        payload = body.get("payload")
        version = body.get("receipt_version")
        if (
            not isinstance(evidence_type, str)
            or not evidence_type.strip()
            or not isinstance(digest, str)
            or not isinstance(payload, dict)
        ):
            return None

        if version == _RECEIPT_VERSION:
            expected = _typed_digest(evidence_type, payload)
            receipt_version = _RECEIPT_VERSION
        elif version is None:
            # Read-only compatibility for evidence receipts created before v2.
            expected = evidence_hash(payload)
            receipt_version = "evidence_receipt.v1"
        else:
            return None

        if digest != expected:
            return None
        if evidence_ref != f"journal://evidence/{digest}":
            return None
        matches.append(EvidenceRecord(
            receipt=EvidenceReceipt(
                event_id=int(event["id"]),
                evidence_type=evidence_type,
                sha256=digest,
                evidence_ref=evidence_ref,
                version=receipt_version,
            ),
            payload=payload,
        ))
    if not matches:
        return None
    return matches[-1]


def evidence_ref_exists(journal: DecisionJournal, evidence_ref: str) -> bool:
    return resolve_evidence(journal, evidence_ref) is not None
