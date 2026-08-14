from __future__ import annotations

from ah.core import AHCore
from ah.model import Domain, Ref


class DomainRouter:
    """MVP semantic routing for external assertions.

    Existing personalized/history-dependent actants make the assertion personalized.
    Otherwise the external semantic assertion is intersubjective (C).
    H is selected only by an explicit H-only integration path.
    """

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def route_external(self, resolved_refs: tuple[Ref, ...]) -> Domain:
        for ref in resolved_refs:
            domain = self.core.store.domain_of(ref.uid)
            if domain in (Domain.P, Domain.H):
                return Domain.P
        return Domain.C
