from __future__ import annotations

from dataclasses import dataclass

from ah.bootstrap import RuntimeServices
from ah.model import Link


@dataclass(frozen=True, slots=True)
class ManualLinkRequest:
    source_uid: str
    target_uid: str
    relation_id: str
    weight: float = 0.25


@dataclass(frozen=True, slots=True)
class ManualLinkResult:
    link: Link
    created: bool


class ManualLinkManager:
    """Create/reuse canonical L between two existing canvas nodes."""

    def __init__(self, services: RuntimeServices) -> None:
        self.services = services

    def create(self, request: ManualLinkRequest) -> ManualLinkResult:
        source_uid = request.source_uid.strip()
        target_uid = request.target_uid.strip()
        relation_id = request.relation_id.strip()
        if not source_uid or not target_uid:
            raise ValueError("Both source and target nodes are required")
        if source_uid == target_uid:
            raise ValueError("Source and target must be different nodes")
        if not relation_id:
            raise ValueError("Relation ID must be non-empty")
        if not 0.0 <= request.weight <= 1.0:
            raise ValueError("Link weight must be in [0, 1]")

        with self.services.operation_lock:
            if not self.services.core.store.has_uid(source_uid):
                raise KeyError(source_uid)
            if not self.services.core.store.has_uid(target_uid):
                raise KeyError(target_uid)
            source = self.services.core.ref(source_uid)
            target = self.services.core.ref(target_uid)
            link, created = self.services.core.ensure_link(
                relation_id, source, target, request.weight
            )
        return ManualLinkResult(link, created)
