# -*- coding: utf-8 -*-
"""Open-set value-generation *mechanism* (V7 §2.3) — D.

The trigger (:mod:`ah.formalizer.open_set_gate`) decides *when* to consider extending a predicate's closed value set; this
module is the bounded **probe** that runs only when the gate fires: it asks the LLM for at most ONE new value and requires
that value to be **grounded in the observed text**. It never invents values, never auto-applies them (the schema extension
is a separate explicit acceptance act), and stays inert below the trigger threshold.

Honesty contract:
- The probe is invoked only when :func:`evaluate_open_set` fires AND a selector is supplied; otherwise it returns ``None``
  without any LLM call.
- A proposal must carry grounding text that actually occurs in one of the miss inputs — an ungrounded value is rejected, not
  recorded (no invention).
- A value duplicating an already-declared value is not an extension and is dropped.
- The result is a *provisional* :class:`ValueProposal`; nothing here mutates any schema or decision state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ValueProposal:
    slot_id: str
    value: str
    grounding_text: str
    source: str = "LLM_PROBE"


def _missed(state, slot_id: str) -> bool:
    for dec in getattr(state, "decisions", {}).values():
        if dec.slot_id == slot_id and dec.outcome == "NO_CANDIDATE":
            return True
    return False


def build_probe_prompt(slot_id: str, miss_texts, existing_values=()) -> str:
    """Bounded English protocol: propose at most one NEW value grounded in the text, or report NONE."""
    lines = [
        "You are extending a closed predicate-value set only when the declared values demonstrably do not fit.",
        f"Slot: {slot_id}",
        f"Already-declared values (do NOT repeat): {', '.join(existing_values) if existing_values else '(none listed)'}",
        "The following inputs produced an honest NO_CANDIDATE on this slot:",
    ]
    lines += [f"- {t}" for t in miss_texts]
    lines += [
        "Propose AT MOST ONE new value that is directly grounded in the text above. Do not invent values without textual evidence.",
        'Respond with strict JSON: {"value": "<new value or null>", "grounding_text": "<the exact text span justifying it>"}',
    ]
    return "\n".join(lines)


def propose_value(slot_id: str, miss_texts, selector, existing_values=()) -> ValueProposal | None:
    """Run the bounded probe. Returns a grounded :class:`ValueProposal`, or ``None`` (no value / ungrounded / duplicate)."""
    if not miss_texts:
        return None
    raw = selector.select(build_probe_prompt(slot_id, miss_texts, existing_values))
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    value = str(parsed.get("value") or "").strip()
    grounding = str(parsed.get("grounding_text") or "").strip()
    if not value:                       # the model reported NONE / no value -> nothing proposed
        return None
    if not grounding:                   # an ungrounded value is rejected at the source (no invention)
        return None
    if value.lower() in {str(v).lower() for v in existing_values}:
        return None                     # a duplicate of a declared value is not an extension
    return ValueProposal(slot_id=slot_id, value=value, grounding_text=grounding)


def verify_proposal(proposal: ValueProposal | None, miss_texts) -> tuple[bool, str]:
    """Verification: the proposal's grounding must actually occur in one of the miss inputs (not invented)."""
    if proposal is None or not proposal.value:
        return False, "EMPTY_PROPOSAL"
    g = proposal.grounding_text.strip()
    if not g:
        return False, "NO_GROUNDING"
    for text in miss_texts:
        if g.lower() in str(text).lower():
            return True, "VERIFIED"
    return False, "GROUNDING_NOT_IN_INPUT"


def maybe_extend(states, slot_id: str = "predicate_value", selector=None, existing_values=(), min_distinct: int = 3):
    """Gate + probe + verify. Returns a verified :class:`ValueProposal` (provisional, NOT auto-applied) or ``None``."""
    from ah.formalizer.open_set_gate import evaluate_open_set

    if selector is None or evaluate_open_set(states, slot_id, min_distinct) is None:
        return None                     # not triggered (or no probe available): nothing proposed, nothing applied
    miss_texts = [getattr(st, "text", "") for st in states if _missed(st, slot_id)]
    proposal = propose_value(slot_id, miss_texts, selector, existing_values)
    ok, _reason = verify_proposal(proposal, miss_texts)
    return proposal if (proposal is not None and ok) else None


__all__ = ["ValueProposal", "build_probe_prompt", "propose_value", "verify_proposal", "maybe_extend"]
