from __future__ import annotations

from dataclasses import dataclass

from ah.core import AHCore
from ah.model import Domain, FunctionSymbol, Group, Hypernode, SemanticEntity


@dataclass(frozen=True, slots=True)
class GCResult:
    requested: tuple[str, ...]
    protected: tuple[str, ...]
    deleted: tuple[str, ...]
    orphan_deleted: tuple[str, ...]


class GarbageCollector:
    """Conservative canonical GC.

    Expired N can be deleted only when no non-link canonical structure points to
    it and it is not part of an H FOLLOW chain. Incident L are removed together
    with deleted endpoints. Orphan cleanup is deliberately conservative: only
    auto-created m/k marked by deterministic integration are eligible.
    """

    def __init__(self, core: AHCore, *, enabled: bool = True, orphan_cleanup: bool = True) -> None:
        self.core = core
        self.enabled = enabled
        self.orphan_cleanup = orphan_cleanup

    def collect(self, expired_candidates: tuple[str, ...]) -> GCResult:
        requested = tuple(sorted(set(expired_candidates)))
        if not self.enabled or not requested:
            return GCResult(requested, (), (), ())

        protected: set[str] = set()
        deletable: set[str] = set()
        for uid in requested:
            if not self.core.store.has_uid(uid):
                continue
            if self._is_protected(uid):
                protected.add(uid)
            else:
                deletable.add(uid)

        removed = self.core.store._delete_uids(deletable)
        deleted_nodes = {uid for uid in deletable if uid in removed}

        orphan_deleted: set[str] = set()
        if self.orphan_cleanup and deleted_nodes:
            orphan_deleted = self._collect_auto_orphans()

        return GCResult(
            requested,
            tuple(sorted(protected)),
            tuple(sorted(removed)),
            tuple(sorted(orphan_deleted)),
        )

    def _is_protected(self, uid: str) -> bool:
        # N used as an actant, g operand or k member is semantically referenced.
        if self.core.store.structural_referrers(uid):
            return True

        # H episodic linkage is historical structure and protects its endpoints.
        for link in (*self.core.store.outgoing_links(uid, "FOLLOW"), *self.core.store.incoming_links(uid, "FOLLOW")):
            source_domain = self.core.store.domain_of(link.source.uid)
            target_domain = self.core.store.domain_of(link.target.uid)
            if Domain.H in {source_domain, target_domain}:
                return True
        return False

    def _collect_auto_orphans(self) -> set[str]:
        removed_total: set[str] = set()
        while True:
            candidates: set[str] = set()
            for domain in Domain:
                for element in self.core.store.elements(domain):
                    if not isinstance(element, (SemanticEntity, Group)):
                        continue
                    if not bool(element.meta.get("gc_auto_created", False)):
                        continue
                    if self.core.store.structural_referrers(element.uid):
                        continue
                    if self.core.store.has_any_link(element.uid):
                        continue
                    candidates.add(element.uid)
            if not candidates:
                break
            removed = self.core.store._delete_uids(candidates)
            removed_total.update(removed)
        return removed_total
