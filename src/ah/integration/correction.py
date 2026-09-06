from __future__ import annotations

from dataclasses import dataclass

from ah.core import AHCore
from ah.model import Domain, Ref, RefKind

from .contracts import ActivationSeedRequest, RefutationRequest, SeedReason


@dataclass(frozen=True, slots=True)
class RefutationCommit:
    refuted_ref: Ref
    false_ref: Ref
    false_created: bool
    activation_seeds: tuple[ActivationSeedRequest, ...]
    refutations: tuple[RefutationRequest, ...]
    unsupported_conclusions: tuple[Ref, ...] = ()


@dataclass(frozen=True, slots=True)
class CorrectionCommit:
    """Explicit semantic correction without destructive history rewriting."""

    target_ref: Ref
    replacement_ref: Ref
    false_ref: Ref
    corrects_ref: Ref
    false_created: bool
    corrects_created: bool
    activation_seeds: tuple[ActivationSeedRequest, ...]
    refutations: tuple[RefutationRequest, ...]
    unsupported_conclusions: tuple[Ref, ...] = ()


@dataclass(frozen=True, slots=True)
class ContradictionCommit:
    """Addressable explicit meta-relation; it does not choose a truth winner."""

    left_ref: Ref
    right_ref: Ref
    contradicts_ref: Ref
    created: bool


class SemanticCorrectionService:
    """Operational meta-semantics for FALSE / CONTRADICTS / CORRECTS.

    The operations preserve the original proposition.  They update admissibility
    through the proof-support sidecar, never by using recency, activation or link
    weight as truth.  The generated g nodes are canonical meta-propositions with
    deterministic FunctionRegistry handlers, while the dependency invalidation is
    runtime/persistence metadata rather than a new AH node kind.
    """

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def _validate_proposition(self, ref: Ref) -> Domain:
        if ref.kind not in {RefKind.N, RefKind.G}:
            raise TypeError("Meta-proposition target must be N or G")
        if not self.core.store.has_uid(ref.uid):
            raise KeyError(ref.uid)
        domain = self.core.store.domain_of(ref.uid)
        if domain is None:
            raise ValueError("Meta-proposition must belong to C/P/H")
        return domain

    def refute(self, target: Ref) -> RefutationCommit:
        # v4 explicitly defines FALSE(N) as meta-refutation of one stored
        # proposition. Compound g corrections use CORRECTS on their addressable
        # roots, but destructive FALSE(g) is intentionally not generalized here.
        if target.kind is not RefKind.N:
            raise TypeError("Explicit refutation target must be N")
        domain = self._validate_proposition(target)

        false_g, created = self.core.ensure_function(domain, "FALSE", (target,))
        false_ref = self.core.ref(false_g.uid)
        unsupported = self.core.invalidate_supports_by_premise(target)
        return RefutationCommit(
            refuted_ref=target,
            false_ref=false_ref,
            false_created=created,
            activation_seeds=(
                ActivationSeedRequest(false_ref, SeedReason.CORRECTION),
            ),
            refutations=(RefutationRequest(target),),
            unsupported_conclusions=unsupported,
        )

    def mark_contradiction(self, left: Ref, right: Ref) -> ContradictionCommit:
        domain = self._validate_proposition(left)
        self._validate_proposition(right)
        if left == right:
            raise ValueError("A proposition cannot contradict itself by identity")
        meta, created = self.core.ensure_function(domain, "CONTRADICTS", (left, right))
        return ContradictionCommit(left, right, self.core.ref(meta.uid), created)

    def correct(self, target: Ref, replacement: Ref) -> CorrectionCommit:
        """Record an explicit correction and invalidate only dependent supports.

        ``replacement`` must already be canonical semantic content.  This method
        does not manufacture/assert it from text, so Main LLM or correction code
        cannot bypass normal perception/integration ownership.
        """

        if target.kind is not RefKind.N:
            raise TypeError("CORRECTS target must be a concrete proposition N")
        domain = self._validate_proposition(target)
        self._validate_proposition(replacement)
        if target == replacement:
            raise ValueError("Correction replacement must differ from target")

        false_g, false_created = self.core.ensure_function(domain, "FALSE", (target,))
        corrects_g, corrects_created = self.core.ensure_function(
            domain, "CORRECTS", (target, replacement)
        )
        false_ref = self.core.ref(false_g.uid)
        corrects_ref = self.core.ref(corrects_g.uid)
        unsupported = self.core.invalidate_supports_by_premise(target)
        return CorrectionCommit(
            target_ref=target,
            replacement_ref=replacement,
            false_ref=false_ref,
            corrects_ref=corrects_ref,
            false_created=false_created,
            corrects_created=corrects_created,
            activation_seeds=(
                ActivationSeedRequest(false_ref, SeedReason.CORRECTION),
                ActivationSeedRequest(corrects_ref, SeedReason.CORRECTION),
            ),
            refutations=(RefutationRequest(target),),
            unsupported_conclusions=unsupported,
        )
