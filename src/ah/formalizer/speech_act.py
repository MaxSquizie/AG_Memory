# -*- coding: utf-8 -*-
"""Speech-act detection (V7 §18 DR27 / A37) — indirect request & interrogative readings.

Closes the PARTIAL gap flagged in IMPLEMENTATION_MAP_V7 (§18 speech-act/modus): the Phase 1 pipeline
detects only indicative/imperative mood, while DR27 requires handling an *indirect request* such as
«Ты не мог бы открыть окно?» — an interrogative cue plus a modal/NEG scope that yields linked
QUERY / COMMAND alternatives.

Contract (honest, no fabrication):
- Detection uses DECLARED structural cues only (terminal ``?`` or declared question words; NEG +
  conditional particle for the indirect-request reading) — never per-word semantic hacks.
- A speech-act reading is a *reading of the utterance*, NOT a world fact: it must NEVER assert that the
  requested action happened (no predicate assertion for the embedded content). The adapter surfaces
  readings as diagnostics; the AH delta stays empty for question content (DR27).
- If no context determines the act, linked alternatives are kept (QUERY + COMMAND), each ungrounded by
  explicit context. An explicit ``request_kind=...`` context fact resolves a single grounded reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechActReading:
    kind: str          # "QUERY" | "COMMAND" | "DECLARATIVE"
    grounded: bool     # True if fixed by explicit context; False if inferred from form only


# Declared structural cues (two-tier invariant: declared + corpus-testable, not per-word semantics).
_QUESTION_WORDS = {"что", "кто", "где", "когда", "почему", "как", "какой", "ли"}
_NEG_MARKERS = {"не", "ни"}
_CONDITIONAL_PARTICLES = {"бы", "б"}


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-zа-яё]+", text.lower()) if w}


def _declared_request_kind(context_facts) -> str | None:
    """Parse an explicit ``request_kind=QUERY|COMMAND`` context fact (the only way to ground a reading)."""
    for fact in context_facts or ():
        m = re.search(r"request_kind\s*=\s*(QUERY|COMMAND)", str(fact), re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def detect_speech_act(text: str, context_facts=()) -> tuple[SpeechActReading, ...]:
    """Return the speech-act reading(s) for ``text``.

    - non-interrogative -> single DECLARATIVE (grounded by form);
    - interrogative with NEG + conditional particle -> linked {QUERY, COMMAND}, both ungrounded;
    - plain interrogative -> single QUERY (grounded by the question form);
    - an explicit ``request_kind=...`` context fact overrides to that single grounded reading.
    """
    t = text.strip()
    words = _words(t)
    declared = _declared_request_kind(context_facts)

    interrogative = t.endswith("?") or bool(words & _QUESTION_WORDS)
    if not interrogative:
        return (SpeechActReading("DECLARATIVE", grounded=True),)

    if declared is not None:
        return (SpeechActReading(declared, grounded=True),)

    indirect_request = bool(words & _NEG_MARKERS) and bool(words & _CONDITIONAL_PARTICLES)
    if indirect_request:
        # Linked alternatives; neither is fixed by context -> both ungrounded. No action asserted.
        return (SpeechActReading("QUERY", grounded=False), SpeechActReading("COMMAND", grounded=False))

    return (SpeechActReading("QUERY", grounded=True),)


def has_linked_alternatives(readings: tuple[SpeechActReading, ...]) -> bool:
    """True when the utterance is an unresolved speech act (multiple linked readings)."""
    return len(readings) > 1 and any(not r.grounded for r in readings)
