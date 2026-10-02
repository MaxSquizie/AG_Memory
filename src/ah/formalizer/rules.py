# -*- coding: utf-8 -*-
"""Declarative structural rule registry (Rev16 implementation audit, CP1).

The SRL core (``pipeline.srl``) is a GENERIC EVALUATOR: it runs the registered
rules in declared order and collects the candidates they produce. ALL language
knowledge lives INSIDE the rule declarations — activation predicate + producer —
never in the evaluation loop. Adding a new structural pattern = registering one
more ``StructuralRule`` (data), never a change to the core (I13 analogue for SRL,
V5 §5.2 p.9 declarative self-audit).

Every produced candidate carries ``ResourceProvenance(pattern_ids=(rule_id,),
resource_versions=...)`` — a fired rule is visible in the trace (§18.2/I27).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ah.formalizer.state import (
    BoundaryCandidate,
    EllipsisCandidate,
    ResourceProvenance,
    TokenHypothesis,
)

_R1_VERSION = "pymorphy3-opencorpora"


@dataclass(frozen=True)
class StructuralRule:
    """One DECLARED structural pattern. ``activate``/``produce`` carry the rule's own
    knowledge (R1 feature predicates, declared signals); the SRL core only calls them."""

    rule_id: str
    description: str
    activate: Callable  # (evs, parses) -> bool
    produce: Callable   # (state, evs, parses) -> list of structural candidates
    resource_versions: dict = field(default_factory=dict)


class RuleRegistry:
    """Ordered set of declared rules. ``register`` appends a new rule WITHOUT any
    change to the evaluation core — extensibility is data, not code (CP1)."""

    def __init__(self, rules=()):
        self._rules = tuple(rules)

    @property
    def rules(self):
        return self._rules

    def register(self, rule: "StructuralRule") -> "RuleRegistry":
        if any(r.rule_id == rule.rule_id for r in self._rules):
            raise ValueError(f"duplicate rule id: {rule.rule_id}")
        self._rules = self._rules + (rule,)
        return self


# --------------------------------------------------------------------------- declared rules

def _has_finite_verb(parses) -> bool:
    """B1's declared structural signal — R1 features only, no lexical knowledge."""
    return any(v.pos == "VERB" and v.tense in ("past", "present", "future") for v in parses)


def _top_is_nominal(parses) -> bool:
    """B1/E1 declared signal: the top-scored parse is a nominal head candidate."""
    if not parses:
        return False
    top = max(parses, key=lambda v: v.score)
    return top.pos in ("NOUN", "ADJF", "NPRO")


def _l1_activate(evs, parses):
    return any(len(e.span.lower()) >= 3 and e.span.lower()[-1] == e.span.lower()[-2] for e in evs)


def _l1_produce(state, evs, parses):
    """Orthographic double-letter hypothesis. keep_as_is is a FIRST-CLASS variant;
    dictionary distance may rank later but never proves a correction (V5 §17.3/§17.5)."""
    out = []
    for i, ev in enumerate(evs):
        s = ev.span.lower()
        if len(s) >= 3 and s[-1] == s[-2]:
            out.append(TokenHypothesis(
                hypothesis_id=f"L{i}", span_ref=ev.span,
                variants=("keep_as_is", ev.span[:-1]),
                provenance=ResourceProvenance(pattern_ids=(rule_l1.rule_id,)),
            ))
    return out


def _b1_produce(state, evs, parses):
    """A finite verb that is NOT the unit's first predicative center opens boundary
    candidates before itself and before its nearest preceding nominal subject."""
    prov = ResourceProvenance(pattern_ids=(rule_b1.rule_id,), resource_versions={"r1": _R1_VERSION})
    centers = [i for i, p in enumerate(parses) if _has_finite_verb(p)]
    out = []
    for c in centers[1:]:
        positions = {c}
        for j in range(c - 1, -1, -1):
            if _top_is_nominal(parses[j]):
                positions.add(j)
                break
        for p in sorted(positions):
            out.append(BoundaryCandidate(
                candidate_id=f"B{p}", position=p, kind="CLAUSE_BOUNDARY",
                evidence=[f"new predicative center '{evs[c].span}' after first center '{evs[centers[0]].span}'"],
                provenance=prov,
            ))
    return out


def _e1_activate(evs, parses):
    if any(_has_finite_verb(p) or any(v.pos == "INFN" for v in p) for p in parses):
        return False
    return any(_top_is_nominal(p) for p in parses)


def _e1_produce(state, evs, parses):
    """A unit with no finite verb/infinitive but with nominals gets a PREDICATE_GAP —
    structural gap only; valency is T2/T3's job [H3]."""
    nominals = [ev.span for ev, p in zip(evs, parses) if _top_is_nominal(p)]
    if not nominals:
        return []
    return [EllipsisCandidate(
        candidate_id="G0", gap_ref=nominals[0], kind="PREDICATE_GAP", antecedent_ref=None,
        evidence=["no finite verb or infinitive in the unit (structural gap)"],
        provenance=ResourceProvenance(pattern_ids=(rule_e1.rule_id,), resource_versions={"r1": _R1_VERSION}),
    )]


def _b1_activate(evs, parses):
    return len([p for p in parses if _has_finite_verb(p)]) >= 2


rule_l1 = StructuralRule(
    "L1_double_letter",
    "orthographic double-letter hypothesis; keep-as-is first-class (V5 §17.3)",
    _l1_activate, _l1_produce,
)
rule_b1 = StructuralRule(
    "B1_new_predicative_center",
    "a finite verb that is not the unit's first predicative center opens boundary candidates",
    _b1_activate, _b1_produce, {"r1": _R1_VERSION},
)
rule_e1 = StructuralRule(
    "E1_predicate_gap",
    "no finite verb/infinitive but nominals present -> PREDICATE_GAP (structural only)",
    _e1_activate, _e1_produce, {"r1": _R1_VERSION},
)


def default_registry() -> RuleRegistry:
    """The declared demo-v1 SRL ruleset [C]. A new pattern = a new entry here or via
    ``register()``; the evaluation core never changes (CP1)."""
    return RuleRegistry((rule_l1, rule_b1, rule_e1))
