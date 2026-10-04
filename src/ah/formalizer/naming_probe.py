# -*- coding: utf-8 -*-
"""V7 port of the ``generalized_naming`` CAPABILITY (not its span-overlap heuristics).

The capability preserved (see ``HEURISTICS_MIGRATE_VS_DROP_AUDIT.md``): naming/identification is ONE
semantic relation realized by three structural families —

  * verbal naming            «Меня зовут Илья»
  * nominal deictic predication  «Я — Илья», «Илья — это я»
  * state deictic predication    «Я являюсь Ильёй»

Python does only the DECLARED structural work: it finds a first-person DEICTIC referent and one or more
source-grounded PREDICATIVE VALUE candidates (a proper-name value is signalled by pymorphy3's ``Name``
grammemes — a language resource, not a per-word rule). A BOUNDED semantic probe then chooses exactly one:

  * NAME_VALUE          the source explicitly assigns one candidate as a name/identity;
  * OTHER_PREDICATION   the value is an ordinary class/property/description (e.g. «Я инженер»);
  * UNCLEAR            neither can be established from this source alone.

Two-tier invariant holds: no lexical-semantic mapping is hard-coded; the deictic set is the closed
first-person singular pronoun set, and the final NAME vs OTHER call is a recorded bounded LLM judgment
(M-ground), never a private rule for specific words.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

# Closed first-person singular deictic referents (declared set — not per-word semantics).
_DEICTIC_1P = frozenset({"я", "меня"})
# Impersonal naming verbs by lemma (declared structural trigger for the verbal family).
_NAMING_VERB_LEMMAS = frozenset({"звать"})

NAMING_DECISIONS = ("NAME_VALUE", "OTHER_PREDICATION", "UNCLEAR")


class NamingProtocolError(ValueError):
    """A malformed / out-of-contract naming-probe response (a failed call, not a verdict)."""


@dataclass
class NamingReading:
    kind: str                      # "verbal" | "deictic_predication"
    referent: str                  # the deictic mention ("я"/"меня")
    values: tuple[str, ...]        # source-grounded predicate-value candidates (verbatim)
    outcome: str | None = None     # NAME_VALUE | OTHER_PREDICATION | UNCLEAR (None until probed)
    name_value: str | None = None  # the chosen value when outcome == NAME_VALUE


def _tokens(text: str) -> list[str]:
    # Strip surrounding punctuation (a trailing period makes pymorphy3 treat the word as OOV)
    # and drop pure-punctuation tokens. The dash is a copula separator, not a token.
    out = []
    for t in text.replace("—", " ").replace("-", " ").split():
        c = t.strip(".,!?;:\"'()«»")
        if c and any(ch.isalnum() for ch in c):
            out.append(c)
    return out


def recognize_naming(text: str, morph=None) -> list[NamingReading]:
    """DECLARED structural recognition of the three naming realizations.

    Returns candidate readings (outcome still None). A reading is emitted only when a first-person
    deictic co-occurs with at least one nominal predicate value; the verbal family additionally needs
    an impersonal naming verb. No semantic filtering happens here — that is the probe's job.
    """
    toks = _tokens(text)
    if not toks:
        return []

    def pos(word: str):
        if morph is None:
            return None, None
        p = morph.parse(word)[0]
        return (p.tag.POS or ""), p.normal_form

    deictics = [t for t in toks if t.lower() in _DEICTIC_1P]
    if not deictics:
        return []

    readings: list[NamingReading] = []
    # Verbal family: an impersonal naming verb (звать) present.
    has_naming_verb = any((pos(t)[0] == "VERB" and pos(t)[1] in _NAMING_VERB_LEMMAS) for t in toks if t.lower() not in _DEICTIC_1P)
    # Nominal predicate values: nouns (a proper name is a noun carrying the Name grammeme).
    nominal_values = [t for t in toks if t.lower() not in _DEICTIC_1P and pos(t)[0] == "NOUN"]

    if has_naming_verb:
        readings.append(NamingReading(kind="verbal", referent=deictics[0], values=tuple(nominal_values)))
    elif nominal_values:
        # Copula / zero-copula deictic predication (есть / являюсь / «Я — Илья»).
        readings.append(NamingReading(kind="deictic_predication", referent=deictics[0], values=tuple(nominal_values)))
    return readings


def _naming_prompt(referent: str, values: Iterable[str]) -> str:
    vals = ", ".join(f'"{v}"' for v in values)
    return (
        "Task: decide whether this source assigns a NAME/IDENTITY to the referent.\n"
        f'Referent (first-person deictic): "{referent}".\n'
        f"Candidate predicate values present in the source: {vals}.\n"
        'Respond with JSON only, exactly one of:\n'
        '{"decision": "NAME_VALUE", "value": "<one candidate verbatim>"}  — the source explicitly names/identifies;\n'
        '{"decision": "OTHER_PREDICATION"}  — the value is an ordinary class/property/description (not a name);\n'
        '{"decision": "UNCLEAR"}  — cannot be established from this source alone.\n'
        'Rules: NAME_VALUE requires exactly one candidate, copied verbatim. Do not invent values.'
    )


def _validate_naming_response(raw: str, values: Iterable[str]) -> tuple[str, str | None]:
    # Reuse the shared transport normalization (strip ONE outer markdown code fence) so both
    # bounded probes treat real-model output identically. A fenced-but-valid payload is accepted;
    # anything else still fails closed.
    from ah.formalizer.selection_protocol import _strip_code_fence
    allowed = set(values)
    try:
        data = json.loads(_strip_code_fence(raw))
    except (json.JSONDecodeError, TypeError):
        raise NamingProtocolError(f"not JSON: {raw!r}") from None
    if not isinstance(data, dict):
        raise NamingProtocolError("response is not a JSON object")
    decision = data.get("decision")
    if decision not in NAMING_DECISIONS:
        raise NamingProtocolError(f"unknown decision {decision!r}")
    if decision == "NAME_VALUE":
        value = data.get("value")
        if value not in allowed:
            raise NamingProtocolError(f"value {value!r} is not one of the source candidates {sorted(allowed)!r}")
        return decision, str(value)
    # OTHER_PREDICATION / UNCLEAR carry no value.
    return decision, None


def naming_probe(selector, reading: NamingReading, context_facts: tuple[str, ...] = ()) -> NamingReading:
    """Bounded semantic probe (M-ground). Fills ``outcome``/``name_value`` on a copy of the reading."""
    if not reading.values:
        return NamingReading(kind=reading.kind, referent=reading.referent, values=(), outcome="UNCLEAR")
    prompt = _naming_prompt(reading.referent, reading.values)
    raw = selector.select(prompt)
    decision, value = _validate_naming_response(raw, reading.values)
    return NamingReading(kind=reading.kind, referent=reading.referent, values=reading.values,
                        outcome=decision, name_value=value if decision == "NAME_VALUE" else None)


def run_naming(text: str, selector, morph=None, context_facts: tuple[str, ...] = ()) -> list[NamingReading]:
    """Recognize the naming construction(s), then probe each. Empty when no deictic+value structure."""
    return [naming_probe(selector, r, context_facts) for r in recognize_naming(text, morph)]
