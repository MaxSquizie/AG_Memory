# -*- coding: utf-8 -*-
"""WP3.2 — Quantifiers (V7 §6.2): alpha-normalization, canonical forms, on-demand instantiation, closed numeric domains.

A quantified formula is a small IR (``Atom`` / ``Quantified``). Alpha-normalization renames bound variables to a canonical pre-order
sequence ``x0, x1, ...`` so that two formulas differing only in variable names compare equal. Canonical forms render EVERY/SOME/NONE and
numeric claims deterministically. Instantiation (FORALL_INST for EVERY, witness substitution for SOME) is performed **only on demand** —
never at commit time — and a numeric claim is evaluated against an explicitly declared *closed* domain (no open-ended counting).

Pure module; the goal channel calls ``instantiate`` when a specific rule needs it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Atom:
    pred: str
    args: tuple = ()


@dataclass(frozen=True)
class Quantified:
    quantifier: str            # EVERY | SOME | NONE | AT_LEAST_N
    variable: str
    body: object               # Atom | Quantified
    count: int = 0            # for AT_LEAST_N

    def __post_init__(self):
        if self.quantifier == "AT_LEAST_N" and self.count < 1:
            raise ValueError("AT_LEAST_N requires a positive count")


def alpha_normalize(node) -> object:
    """Rename bound variables to x0, x1, ... in pre-order of their binding; free variables pass through unchanged.

    A single pass carries a rename map (old bound name -> canonical). When a binding is met its variable is assigned the next
    canonical name BEFORE its body is traversed (pre-order), so inner bindings see outer ones already renamed and no capture occurs.
    """
    counter = itertools.count()

    def walk(n, rename):
        if isinstance(n, Quantified):
            new_name = f"x{next(counter)}"
            child = dict(rename)
            child[n.variable] = new_name
            return Quantified(n.quantifier, new_name, walk(n.body, child), n.count)
        if isinstance(n, Atom):
            args = tuple(Var(rename.get(a.name, a.name)) if isinstance(a, Var) else a for a in n.args)
            return Atom(n.pred, args)
        raise TypeError(f"unknown formula node {n!r}")

    return walk(node, {})


def _subst(node, old: str | None, new):  # used only by instantiate; old is the bound variable name
    if isinstance(node, Quantified):
        body = _subst(node.body, old, new)
        var = node.variable
        if old is not None and var == old:
            var = new.name if isinstance(new, Var) else str(new)   # shadowing guard (rare in tests)
        return Quantified(node.quantifier, var, body, node.count)
    if isinstance(node, Atom):
        args = tuple(new if (isinstance(a, Var) and old is not None and a.name == old) else a for a in node.args)
        return Atom(node.pred, args)
    raise TypeError(f"unknown formula node {node!r}")


def instantiate(quantified: Quantified, witness):
    """On-demand instantiation (never at commit). EVERY -> body[x := witness]; SOME -> same. Others are not directly instantiable."""
    if quantified.quantifier not in ("EVERY", "SOME"):
        raise ValueError(f"cannot directly instantiate {quantified.quantifier}")
    return _subst(quantified.body, quantified.variable, Var(str(witness)))


def canonical_form(node) -> str:
    n = alpha_normalize(node)

    def render(x):
        if isinstance(x, Quantified):
            inner = render(x.body)
            if x.quantifier == "EVERY":
                return f"∀{x.variable}.{inner}"
            if x.quantifier == "SOME":
                return f"∃{x.variable}.{inner}"
            if x.quantifier == "NONE":
                return f"¬∃{x.variable}.{inner}"
            if x.quantifier == "AT_LEAST_N":
                return f"≥{x.count} {inner}"
            raise ValueError(f"unknown quantifier {x.quantifier}")
        if isinstance(x, Atom):
            args = ",".join(a.name if isinstance(a, Var) else str(a) for a in x.args)
            return f"{x.pred}({args})"
        raise TypeError(f"unknown formula node {x!r}")

    return render(n)


class NumericDomain:
    """A declared closed domain for numeric claims; counting is bounded by the domain, never open-ended."""

    def __init__(self, values):
        self.values = list(values)

    def satisfy(self, holds) -> int:
        """Count domain values v for which holds(v) is true (closed-domain counting)."""
        return sum(1 for v in self.values if holds(v))


if __name__ == "__main__":  # pragma: no cover - quick sanity
    f = Quantified("EVERY", "x", Atom("P", (Var("x"),)))
    print(canonical_form(f), "->", canonical_form(instantiate(f, "a")))
