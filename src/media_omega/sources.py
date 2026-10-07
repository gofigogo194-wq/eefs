from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .observations import ContentObservation


class ObservationSource(Protocol):
    name: str

    def fetch(self) -> list[ContentObservation]:
        """Return normalized observations with provenance."""
        ...


@dataclass
class StaticObservationSource:
    observations: list[ContentObservation]
    name: str = "static-fixture"

    def fetch(self) -> list[ContentObservation]:
        for item in self.observations:
            item.validate()
        return list(self.observations)


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, ObservationSource] = {}

    def register(self, source: ObservationSource) -> None:
        if not source.name.strip():
            raise ValueError("source name is required")
        if source.name in self._sources:
            raise ValueError(f"duplicate source: {source.name}")
        self._sources[source.name] = source

    def collect(self) -> list[ContentObservation]:
        result: list[ContentObservation] = []
        for name in sorted(self._sources):
            batch = self._sources[name].fetch()
            for item in batch:
                item.validate()
                if not item.evidence_ref.startswith(("http://", "https://", "fixture://", "api://")):
                    raise ValueError("unsupported evidence provenance scheme")
            result.extend(batch)
        return result
