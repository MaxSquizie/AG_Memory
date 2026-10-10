"""Effective lexical inference policy, independent of optional AH metadata.

UNLINKED content admits exact source/role/scope attestation and cannot license
canonical inference or equivalence. Known-content rule eligibility continues to
be checked by the registered rule, proof and temporal-license machinery.
This view grants no truth support and never changes the graph.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


EXACT_ATTESTATION = "EXACT_ATTESTATION"
OPEN_LEXICAL_CAPABILITIES = (EXACT_ATTESTATION,)


@dataclass(frozen=True, slots=True)
class NodeInferencePolicy:
    # Explicit lexical capabilities; not an enumeration of known-content rules.
    capabilities: tuple[str, ...]
    exact_attestation_only: bool


_OPEN = NodeInferencePolicy(OPEN_LEXICAL_CAPABILITIES, True)
_CANONICAL = NodeInferencePolicy((), False)


def node_inference_policy(node: Mapping) -> NodeInferencePolicy:
    """Read the canonical semantic status, not unvalidated capability flags.

    The policy is the same for asserted and structural UNLINKED content.
    Visibility and attestation matching remain separate runtime checks.
    """
    return _OPEN if node.get("semantic_status") == "UNLINKED" else _CANONICAL
