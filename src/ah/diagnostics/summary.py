from __future__ import annotations

from dataclasses import dataclass

from ah.core import AHCore
from ah.ignition import IgnitionEngine
from ah.model import Domain, RefKind


@dataclass(frozen=True, slots=True)
class RuntimeSummary:
    tick: int
    symbols: int
    elements_by_domain: dict[str, int]
    elements_by_kind: dict[str, int]
    links: int
    workspace: int
    pending_impulses: int
    pending_refutations: int


class RuntimeDiagnostics:
    def __init__(self, core: AHCore, ignition: IgnitionEngine) -> None:
        self.core = core
        self.ignition = ignition

    def summary(self) -> RuntimeSummary:
        by_domain = {d.value: len(self.core.store.elements(d)) for d in Domain}
        by_kind = {kind.value: 0 for kind in RefKind}
        for uid in self.core.store.all_uids():
            by_kind[self.core.store.kind_of(uid).value] += 1
        snap = self.ignition.export_snapshot(include_pending=True)
        return RuntimeSummary(
            tick=snap.tick_index,
            symbols=by_kind[RefKind.S.value],
            elements_by_domain=by_domain,
            elements_by_kind=by_kind,
            links=by_kind[RefKind.L.value],
            workspace=len(self.ignition.workspace_refs()),
            pending_impulses=len(snap.incoming),
            pending_refutations=len(snap.pending_refutations),
        )
