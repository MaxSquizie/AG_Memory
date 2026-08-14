from __future__ import annotations

from ah.core import AHCore
from ah.model import Ref


class WorkspaceView:
    def __init__(self, core: AHCore, threshold: float) -> None:
        self.core = core
        self.threshold = threshold

    def refs(self) -> tuple[Ref, ...]:
        active: list[Ref] = []
        for uid, runtime in self.core.store.runtime_items():
            if runtime.excitation > self.threshold:
                active.append(self.core.ref(uid))
        active.sort(key=lambda ref: ref.uid)
        return tuple(active)
