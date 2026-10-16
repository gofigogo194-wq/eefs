from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json


@dataclass(frozen=True)
class PublicationPackage:
    entity_id: str
    plan_id: str
    manifest_ref: str
    verification_ref: str
    platform: str
    title: str
    description: str
    visibility: str
    scheduled_at: str
    schedule_id: str
    version: str = "schedule.v2"

    def payload(self) -> dict:
        return {
            "version": self.version,
            "entity_id": self.entity_id,
            "plan_id": self.plan_id,
            "manifest_ref": self.manifest_ref,
            "verification_ref": self.verification_ref,
            "platform": self.platform,
            "title": self.title,
            "description": self.description,
            "visibility": self.visibility,
            "scheduled_at": self.scheduled_at,
            "schedule_id": self.schedule_id,
            "dry_run_only": True,
        }


def prepare_publication(plan, manifest_ref: str, verification_ref: str,
                        scheduled_at: str, description: str = "",
                        visibility: str = "private") -> PublicationPackage:
    if plan.platform != "youtube":
        raise ValueError("only YouTube dry-run scheduling is supported")
    if visibility != "private":
        raise ValueError("dry-run only permits private visibility")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValueError("description must be text of at most 5000 characters")
    if not isinstance(plan.title, str) or not 1 <= len(plan.title.strip()) <= 100:
        raise ValueError("YouTube title must be 1–100 characters")
    if not isinstance(scheduled_at, str):
        raise ValueError("scheduled_at must be an ISO timestamp")
    try:
        stamp = datetime.fromisoformat(scheduled_at)
    except ValueError as exc:
        raise ValueError("scheduled_at must be ISO 8601") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("scheduled_at needs an explicit timezone")
    if stamp.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise ValueError("scheduled_at must be in the future")
    normalized = stamp.astimezone(timezone.utc).isoformat()
    fields = {
        "entity_id": plan.opportunity_id,
        "plan_id": plan.id,
        "manifest_ref": manifest_ref,
        "verification_ref": verification_ref,
        "platform": plan.platform,
        "title": plan.title,
        "description": description,
        "visibility": visibility,
        "scheduled_at": normalized,
    }
    identity = sha256(json.dumps(
        fields, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return PublicationPackage(**fields, schedule_id=f"schedule-{identity[:32]}")


def dry_run_receipt(package: PublicationPackage) -> dict:
    """No provider transport, no credentials and no network side effects."""
    return {
        "version": "publish_dry_run.v1",
        "entity_id": package.entity_id,
        "schedule_id": package.schedule_id,
        "platform": package.platform,
        "would_publish": True,
        "published": False,
        "remote_id": None,
        "mode": "DRY_RUN",
    }
