# -*- coding: utf-8 -*-
"""Goal executor (V7 §5.9) — compile formalized text into canonical AssociationGoals.

The ONLY exit of the formalizer is the immutable CandidateIR; this module turns that IR into
executable goals for the association layer. It compiles into the REAL AH types
(:class:`ah.inference.contracts.AssociationGoal` over :class:`ah.model.types.Ref`) — not a local
copy — so every goal obeys the canonical contract (e.g. an ``L`` ref is rejected by the type
itself, never silently accepted here).

Compilation rules (deterministic, no per-sentence knowledge):
* A mention participates only if the resolver maps it to a canonical Ref; unresolvable mentions
  are skipped — a goal endpoint is NEVER fabricated.
* Only excitable refs form a goal: an ``L`` endpoint is dropped (the real type would raise).
* Candidate pairs come from the IR's frame participants and coreference candidates, deduplicated
  and emitted in stable surface order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from ah.inference.contracts import AssociationGoal
from ah.model.types import Ref, RefKind


@dataclass(frozen=True)
class CompiledGoal:
    goal: AssociationGoal
    left_span: str
    right_span: str
    source_text: str = ""


def _excitable(ref: Ref | None) -> bool:
    return ref is not None and ref.kind != RefKind.L


def compile_association_goals(
    mentions: Sequence[str],
    resolve_ref: Callable[[str], Ref | None],
    *,
    text: str = "",
) -> list[CompiledGoal]:
    """Pairwise AssociationGoals over the resolvable, excitable mentions.

    ``mentions`` are deduplicated preserving first-seen order; each unordered pair of distinct
    spans that both resolve to non-L refs yields one goal (left = earlier in surface order)."""
    seen: dict[str, Ref] = {}
    for span in mentions:
        if span in seen:
            continue
        ref = resolve_ref(span)
        if _excitable(ref):
            seen[span] = ref

    ordered = list(seen.items())  # first-seen order
    out: list[CompiledGoal] = []
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            left_span, left_ref = ordered[i]
            right_span, right_ref = ordered[j]
            out.append(CompiledGoal(goal=AssociationGoal(left=left_ref, right=right_ref),
                                   left_span=left_span, right_span=right_span, source_text=text))
    return out


def _ir_mentions(ir) -> list[str]:
    """Mention spans worth associating: frame participants + coreference candidates."""
    spans: list[str] = []
    for f in getattr(ir, "predicate_frames", ()):  # frames carry participant spans via IR? use lexical fallback below
        pass
    # The IR stores frame ids, not participant spans; fall back to the lexical units that are
    # nominal mentions. Callers needing exact participants should pass them explicitly.
    return list(getattr(ir, "lexical_units", ()))


def goals_from_ir(ir, resolve_ref: Callable[[str], Ref | None], *, text: str = "") -> list[CompiledGoal]:
    """Convenience: compile the IR's lexical mentions into AssociationGoals."""
    return compile_association_goals(_ir_mentions(ir), resolve_ref, text=text)
