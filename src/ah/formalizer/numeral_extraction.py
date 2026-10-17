# -*- coding: utf-8 -*-
"""Numerical interpretation of a caller-selected quantity window.

Only bare integer digits or a single declared cardinal have a deterministic
value. A compound expression is interpreted as a whole with source context;
independent token values are never summed into an invented quantity.
"""

from __future__ import annotations

import json
import re

# Declared language resource [numeral_lexicon_v1]: Russian cardinal lemmas -> base value.
# Standard forms 0..1000; the long tail is resolved by the bounded probe, not by growing this table.
NUMERAL_LEXICON_V1: dict[str, int] = {
    "ноль": 0,
    "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
    "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
    "восемнадцать": 18, "девятнадцать": 19,
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500,
    "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
    "тысяча": 1000,
}

NUMERAL_LEX_VERSION = "numeral_lexicon_v1"


class NumeralProbeError(Exception):
    """A bounded probe returned a malformed response (not the strict {\"value\": int|null} contract)."""


def build_numeral_probe_prompt(surface: str, lemma: str | None, context: str = "") -> str:
    """Bounded lexical-semantic probe. Asks whether the whole target denotes an exact count;
    expects strict JSON {"value": <integer>} or {"value": null}. No free-form generation."""
    return (
        "Determine the exact nonnegative integer count expressed by the selected quantity as a WHOLE.\n"
        f"TARGET quantity: {surface!r}\n"
        f"CONTEXT (evidence only): {context!r}\n"
        f"Lemma (if known): {lemma!r}\n"
        'If this entire expression denotes one exact integer quantity, respond with JSON {"value": <integer>}.\n'
        'If it does not denote a specific integer (not a quantity, a range, a bound, a name, or a fuzzy quantity), '
        'respond with JSON {"value": null}.\n'
        "Respond with the JSON object only — no prose."
    )


def parse_numeral_probe_response(raw: str) -> int | None:
    """Parse the strict probe contract. Returns the integer, or None on an explicit refusal
    ({"value": null}). Raises NumeralProbeError on anything that is not the exact contract."""
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"value"}:
        raise NumeralProbeError(f"probe response must be exactly {{'value': ...}}; got {data!r}")
    value = data["value"]
    if value is None:
        return None  # explicit refusal — a first-class outcome, not an error
    if isinstance(value, bool) or not isinstance(value, int) or value<0:
        raise NumeralProbeError(f"probe 'value' must be an integer or null; got {value!r}")
    return value


class NumeralProbe:
    """A bounded LLM probe over the same low-level ``select(prompt) -> raw JSON`` interface as the rest of
    the pipeline (so a real backend and a test double are interchangeable). Provider unavailability is an
    honest refusal (None), never a fabricated value."""

    def __init__(self, select):
        self._select = select  # callable: (prompt: str) -> raw JSON str; may raise on provider failure

    def probe(self, surface: str, lemma: str | None = None, *, context: str = "") -> int | None:
        try:
            raw = self._select(build_numeral_probe_prompt(surface, lemma, context))
        except Exception:  # provider unavailable / transport error -> honest refusal, not a value
            return None
        return parse_numeral_probe_response(raw)


def _lemma_of(ev) -> str | None:
    """Never turn an analyzer prediction or ambiguous lemma into a table fact."""
    if hasattr(ev,'variants'):
        variants=ev.variants
        if not variants or any(v.origin!='DICTIONARY' for v in variants):return None
        lemmas={v.lemma for v in variants}
        return next(iter(lemmas)) if len(lemmas)==1 else None
    return getattr(ev, "lemma", None)


def _surface_of(ev) -> str:
    span = getattr(ev, "span", None)
    if isinstance(span, tuple):
        return span[0] if span else ""
    return span or ""


# Only bare digits are an unambiguous integer literal in a selected quantity.
# Separators, decimals, ordinals and words require their own contextual evidence.
_DIGIT_RE = re.compile(r"^[0-9]+$")


def _digit_value(surface: str) -> int | None:
    """Read an unambiguous integer literal directly from the surface form (orthographic rule).
    Returns the integer, or None when the token is not a clean cardinal literal."""
    s = (surface or "").strip()
    if not _DIGIT_RE.match(s):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def extract_cardinal_value(
    evs,
    start: int = 0,
    end: int | None = None,
    table: dict[str, int] = NUMERAL_LEXICON_V1,
    probe: NumeralProbe | None = None,
    max_probes: int = 3,
    sources: list | None = None,
) -> int | None:
    """The caller owns quantity boundaries; no scanning for known words.

    A multiword or unfamiliar expression needs one contextual judgment, even
    when its component words have declared standalone values.
    """
    stop=len(evs) if end is None else min(end,len(evs))
    selected=list(evs[start:stop])
    if not selected:return None
    surface=' '.join(_surface_of(e) for e in selected)
    if len(selected)==1:
        value=_digit_value(surface)
        origin='digits'
        if value is None:
            value=table.get(_lemma_of(selected[0]));origin='table'
        if value is not None:
            if sources is not None:sources.append((origin,value))
            return value
    if probe is None or max_probes<1:return None
    value=probe.probe(surface,None,context=' '.join(_surface_of(e) for e in evs))
    if value is not None and sources is not None:sources.append(('probe',value))
    return value
