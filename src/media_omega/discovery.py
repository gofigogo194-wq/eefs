from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class DiscoveryItem:
    platform: str
    content_id: str
    creator_id: str
    title: str
    published_at: str
    evidence_ref: str


class DiscoverySource(Protocol):
    def discover(self, query: str) -> list[DiscoveryItem]:
        ...


@dataclass(frozen=True)
class DiscoveryPolicy:
    max_candidates: int = 25
    min_title_length: int = 3

    def validate(self) -> None:
        if not 1 <= self.max_candidates <= 50:
            raise ValueError("max_candidates must be between 1 and 50")
        if self.min_title_length < 1:
            raise ValueError("min_title_length must be positive")


def select_candidates(items: list[DiscoveryItem], policy: DiscoveryPolicy | None = None) -> list[DiscoveryItem]:
    policy = policy or DiscoveryPolicy()
    policy.validate()
    seen: set[tuple[str, str]] = set()
    result: list[DiscoveryItem] = []
    for item in items:
        key = (item.platform, item.content_id)
        if key in seen:
            continue
        if len(item.title.strip()) < policy.min_title_length:
            continue
        if not item.evidence_ref.strip():
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= policy.max_candidates:
            break
    return result
