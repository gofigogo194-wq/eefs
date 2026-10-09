from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, GateResult


@dataclass(frozen=True)
class PublisherDryRunResult:
    schedule_id: str
    entity_id: str
    published: bool = False
    remote_id: None = None
    mode: str = "DRY_RUN"
    version: str = "publisher_adapter_dry_run.v1"


class YouTubeDryRunAdapter:
    """Offline adapter. No HTTP transport, credentials, or upload methods."""

    name = "youtube-dry-run"

    def prepare(self, package: dict, preflight: GateResult) -> PublisherDryRunResult:
        if not isinstance(package, dict):
            raise ValueError("canonical schedule payload required")
        if (
            package.get("version") != "schedule.v2"
            or package.get("platform") != "youtube"
            or package.get("visibility") != "private"
            or package.get("dry_run_only") is not True
            or not isinstance(package.get("schedule_id"), str)
            or not package["schedule_id"].startswith("schedule-")
            or not isinstance(package.get("entity_id"), str)
            or not package["entity_id"].strip()
        ):
            raise ValueError("only canonical private YouTube dry-run packages allowed")
        if not isinstance(preflight, GateResult) or preflight.decision is not Decision.ACCEPT:
            raise ValueError("fresh successful media preflight required")
        return PublisherDryRunResult(
            schedule_id=package["schedule_id"],
            entity_id=package["entity_id"],
        )
