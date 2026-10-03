# -*- coding: utf-8 -*-
"""WP0.6 (remainder) — §12/§17 integration IR + legacy bridge for the G1 adapter tests.

``IntegrationCandidateIRV2`` is the V2 staging schema (§17): the formalizer's canonical output staged for
atomic promotion to AH. A ``StagedElement.kind=STRUCTURAL`` carries a planned EnsureOpenTemplate with
epistemic=UNATTACHED and EMPTY support_refs (no AddRootSupport, §7.5). Legacy round-trip (§12) is LOSSLESS
only when :func:`can_encode_legacy_graph` holds; otherwise the bridge reports ADAPTER_NOT_COVERED rather than
silently dropping content.

This module is pure: it performs no store writes and calls no LLM. It defines the staging IR, the legacy
encodability predicate, and a lossless encode/decode round-trip for the encodable subset — the two remaining
G1 adapter cases (``legacy_roundtrip``, ``v2_integration``).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


# Payload kinds the product PerceptionResult can carry: asserted relations, nominal relations, quantifiers,
# temporal scopes and proposition operators. What it CANNOT carry (no legacy field): an UNLINKED open template
# (planned EnsureOpenTemplate), a typed UsageLink layer (§3), or a V2 candidate-source trace (§17). Those make
# the IR non-legacy-encodable -> ADAPTER_NOT_COVERED, never silent loss.
_LEGACY_PAYLOAD_KINDS = frozenset(
    {"ASSERTION", "NOMINAL_RELATION", "QUANTIFIER", "TEMPORAL_SCOPE", "PROPOSITION"}
)


@dataclass(frozen=True)
class StagedElement:
    """One staged element of the V2 IR (§17).

    ``kind`` is ASSERTION | QUERY | GOAL | STRUCTURAL. A STRUCTURAL element (planned EnsureOpenTemplate) MUST be
    epistemically UNATTACHED and carry EMPTY support_refs — it asserts no fact, so there is no AddRootSupport."""

    kind: str
    payload: dict
    epistemic: str = "ASSERTED"          # for STRUCTURAL this MUST be UNATTACHED (§7.5)
    support_refs: tuple[str, ...] = ()   # EMPTY for STRUCTURAL — no root support (§17)
    source_span: str = ""

    def __post_init__(self) -> None:
        if self.kind == "STRUCTURAL":
            if self.epistemic != "UNATTACHED":
                raise ValueError("a STRUCTURAL staged element must be epistemically UNATTACHED (§7.5)")
            if self.support_refs:
                raise ValueError("a STRUCTURAL staged element has no root support (empty support_refs, §17)")


@dataclass(frozen=True)
class IntegrationCandidateIRV2:
    """The V2 staging schema (§17). ``schema_version`` is fixed to "v7"."""

    schema_version: str = "v7"
    observation_id: str = ""
    interpretation_version: int = 0
    snapshot_id: str = ""
    elements: tuple[StagedElement, ...] = ()
    goals: tuple[dict, ...] = ()
    coverage_status: str = ""
    candidate_source_trace_refs: tuple[str, ...] = ()  # NO_CANDIDATE -> serialized into ObservationRecord + canonical hash (§17)
    diagnostics: tuple[str, ...] = ()
    provenance: dict = field(default_factory=dict)


def can_encode_legacy_graph(ir: IntegrationCandidateIRV2) -> bool:
    """§12 — the legacy PerceptionResult round-trips this IR losslessly only if EVERY element is a plain
    asserted/nominal/quantifier/temporal/proposition payload AND there is no V2 candidate-source trace.

    A STRUCTURAL (planned EnsureOpenTemplate) element, any non-legacy payload kind, or a non-empty
    ``candidate_source_trace_refs`` -> False (the content has no legacy home)."""
    for el in ir.elements:
        if el.kind == "STRUCTURAL":
            return False  # planned open template is not representable in the legacy graph
        if el.payload.get("payload_kind") not in _LEGACY_PAYLOAD_KINDS:
            return False
    if ir.candidate_source_trace_refs:
        return False  # a NO_CANDIDATE source trace is V2-only content
    return True


def encode_legacy(ir: IntegrationCandidateIRV2) -> dict | None:
    """Lossless legacy encoding. Returns the plain-dict legacy graph when encodable, else ``None`` — the caller
    must then surface ADAPTER_NOT_COVERED and never silently drop content."""
    if not can_encode_legacy_graph(ir):
        return None
    return {
        "schema_version": ir.schema_version,
        "observation_id": ir.observation_id,
        "interpretation_version": ir.interpretation_version,
        "snapshot_id": ir.snapshot_id,
        "elements": [dataclasses.asdict(el) for el in ir.elements],
        "goals": list(ir.goals),
        "coverage_status": ir.coverage_status,
        "candidate_source_trace_refs": list(ir.candidate_source_trace_refs),  # empty when encodable
        "diagnostics": list(ir.diagnostics),
        "provenance": dict(ir.provenance),
    }


def decode_legacy(graph: dict) -> IntegrationCandidateIRV2:
    """Reconstruct the IR from a legacy encoding (inverse of :func:`encode_legacy`)."""
    return IntegrationCandidateIRV2(
        schema_version=graph["schema_version"],
        observation_id=graph.get("observation_id", ""),
        interpretation_version=graph.get("interpretation_version", 0),
        snapshot_id=graph.get("snapshot_id", ""),
        elements=tuple(StagedElement(**e) for e in graph.get("elements", ())),
        goals=tuple(graph.get("goals", ())),
        coverage_status=graph.get("coverage_status", ""),
        candidate_source_trace_refs=tuple(graph.get("candidate_source_trace_refs", ())),
        diagnostics=tuple(graph.get("diagnostics", ())),
        provenance=dict(graph.get("provenance", {})),
    )


def legacy_roundtrip(ir: IntegrationCandidateIRV2) -> tuple[bool, object]:
    """§12 — returns ``(ok, result)``.

    * ``ok=False`` with ``"ADAPTER_NOT_COVERED"`` when the IR is not legacy-encodable (no silent loss).
    * ``ok=True`` with the reconstructed IR when encodable; the decode(encode(ir)) round-trips field-for-field."""
    if not can_encode_legacy_graph(ir):
        return False, "ADAPTER_NOT_COVERED"
    back = decode_legacy(encode_legacy(ir))  # type: ignore[arg-type]
    for a, b in zip(ir.elements, back.elements):
        if dataclasses.asdict(a) != dataclasses.asdict(b):
            return False, "ROUNDTRIP_LOSS"  # unreachable for the encodable subset; guards against silent drift
    return True, back
