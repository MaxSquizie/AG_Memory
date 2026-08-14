from __future__ import annotations

from dataclasses import dataclass

from ah.core import AHCore
from ah.model import Ref, RefKind

from .contracts import ActivationSeedRequest, RefutationRequest, SeedReason


@dataclass(frozen=True, slots=True)
class RefutationCommit:
    refuted_ref: Ref
    false_ref: Ref
    false_created: bool
    activation_seeds: tuple[ActivationSeedRequest, ...]
    refutations: tuple[RefutationRequest, ...]


class SemanticCorrectionService:
    """Canonical semantic supersession for explicit refutation.

    The old N is preserved. FALSE(N) is stored in the same semantic domain and
    becomes the newly stimulated representation. N.w is *not* edited here; a
    RefutationRequest is handed to Ignition so h_N remains the only plasticity
    mechanism that performs the strong weight correction.
    """

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def refute(self, target: Ref) -> RefutationCommit:
        if target.kind is not RefKind.N:
            raise TypeError("Explicit refutation target must be N")
        if not self.core.store.has_uid(target.uid):
            raise KeyError(target.uid)
        domain = self.core.store.domain_of(target.uid)
        if domain is None:
            raise ValueError("N must belong to C/P/H")

        false_g, created = self.core.ensure_function(domain, "FALSE", (target,))
        false_ref = self.core.ref(false_g.uid)
        return RefutationCommit(
            refuted_ref=target,
            false_ref=false_ref,
            false_created=created,
            activation_seeds=(
                ActivationSeedRequest(false_ref, SeedReason.CORRECTION),
            ),
            refutations=(RefutationRequest(target),),
        )
