# -*- coding: utf-8 -*-
"""Reader contract (V7 §7.4 / §17) — E: a fact-requiring goal is satisfied ONLY by an admissible, live record.

The invariant this module makes executable: when a goal asks "is proposition P true?", the answer YES may come only
from evidence that actually *asserts* P as a committed fact (a LIVE ASSERTED record with a valid proof path). The other
evidence kinds must NOT satisfy a fact-requiring goal by default:

- **HYPOTHETICAL** — a node held only as a hypothesis, never asserted;
- **EMBEDDED**  — a proposition occurring inside another construction (a subordinate clause, an object of "said that…"),
  not asserted at the top level;
- **OBSERVATION_RECORD** — candidate evidence of an *excluded* fragment: it lives in the observation channel and never
  enters the canonical store as a fact.

None of these may flip a goal to YES unless the caller explicitly widens admissibility (``allow_kinds``). With no
admissible live record the answer is UNKNOWN (open world — there is no silent NO, and non-admissible evidence is reported
as such rather than silently used). This mirrors §7.4's "effective visibility = LIVE ∧ valid proof path" and the rule that
candidate evidence does not enter AH.

Pure module; deterministic for a fixed record set.
"""

from __future__ import annotations

from dataclasses import dataclass


#: The only kind that satisfies a fact-requiring goal by default: an asserted, committed fact.
DEFAULT_FACT_KINDS = frozenset({"ASSERTED"})

#: All evidence kinds the reader may encounter (for reporting / explicit allowance).
ALL_KINDS = frozenset({"ASSERTED", "HYPOTHETICAL", "EMBEDDED", "OBSERVATION_RECORD"})


@dataclass(frozen=True)
class FactRecord:
    record_id: str
    proposition: str          # canonical proposition key the record speaks about
    kind: str                # ASSERTED | HYPOTHETICAL | EMBEDDED | OBSERVATION_RECORD
    status: str = "LIVE"     # LIVE | SUPERSEDED | RETRACTED


def answer_fact_goal(records, proposition: str, allow_kinds=DEFAULT_FACT_KINDS) -> dict:
    """Answer a fact-requiring goal for ``proposition``.

    YES only from a LIVE record whose kind is in ``allow_kinds`` (default: ASSERTED). Otherwise UNKNOWN — with an honest
    reason distinguishing "no live record at all" from "only non-admissible evidence exists". Non-admissible kinds are
    never used to produce YES unless explicitly allowed.
    """
    for rec in records:
        if rec.proposition == proposition and rec.status == "LIVE" and rec.kind in allow_kinds:
            return {"answer": "YES", "satisfied_by": rec.record_id, "kind": rec.kind}

    nonadmissible = [r for r in records
                     if r.proposition == proposition and r.status == "LIVE" and r.kind not in allow_kinds]
    if nonadmissible:
        return {"answer": "UNKNOWN", "reason": "NON_ADMISSIBLE_EVIDENCE_ONLY",
                "kinds_present": sorted({r.kind for r in nonadmissible})}
    return {"answer": "UNKNOWN", "reason": "NO_LIVE_RECORD"}


__all__ = ["FactRecord", "answer_fact_goal", "DEFAULT_FACT_KINDS", "ALL_KINDS"]
