# -*- coding: utf-8 -*-
"""WP3.2 — Cardinal numeral extraction (declared seed resource + bounded LLM probe).

Empirical basis (pymorphy3/OpenCorpora): Russian numerals have NO reliable morphological value signal —
POS is inconsistent (2-9/ten/twenty parse as NUMR, but сто/тысяча/миллион/ноль parse as NOUN and один
as ADJF) and no NUMB* grammeme is exposed. Therefore the integer VALUE of a numeral cannot be read from
the tagset; it must come from one of the two channels the project invariant sanctions for lexical-semantic
mappings: (a) a declared language resource, or (b) a bounded LLM probe.

Three layers, in priority order — no per-word logic in code:
  * digit literals     : a token whose surface form IS an unambiguous numeric literal ('52', '1 000') reads
    straight to its integer. This is an ORTHOGRAPHIC/structural rule (not lexical-semantic, not per-word):
    digits carry no ambiguity, so they need neither the seed table nor a model.
  * NUMERAL_LEXICON_V1 : the DECLARED SEED RESOURCE for spelled-out numerals. A single numeral token maps to
    its base value deterministically; adjacent numerals compose additively ('двадцать три' = 20+3, 'сто пять'
    = 100+5).
  * bounded probe      : for a token NOT in the seed that is structurally a numeral candidate (POS == NUMR),
    a BOUNDED model judgment resolves its value. The probe is bounded three ways — by the extraction window,
    by the POS==NUMR candidate gate, and by an explicit call budget. A refusal (or provider unavailability)
    contributes nothing and terminates the run: an unknown numeral is never assigned a guessed value.

Provenance: each resolved component records its origin — 'digits' (orthographic literal, unambiguous),
'table' (declared seed resource = R) or 'probe' (model judgment = M). Probe-derived values are MODEL
JUDGMENT, not declared fact; downstream must treat them as such, unlike digit/seed values.
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


def build_numeral_probe_prompt(surface: str, lemma: str | None) -> str:
    """Bounded lexical-semantic probe. Asks ONLY whether one token denotes a specific integer count;
    expects strict JSON {"value": <integer>} or {"value": null}. No free-form generation."""
    return (
        "You are resolving the numeric value of a single Russian numeral token.\n"
        f"Token surface form: {surface!r}\n"
        f"Lemma (if known): {lemma!r}\n"
        'If this token denotes a specific integer quantity, respond with JSON {"value": <integer>}.\n'
        'If it does not denote a specific integer (not a numeral, or an unbounded/fuzzy quantity), '
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
    if isinstance(value, bool) or not isinstance(value, int):
        raise NumeralProbeError(f"probe 'value' must be an integer or null; got {value!r}")
    return value


class NumeralProbe:
    """A bounded LLM probe over the same low-level ``select(prompt) -> raw JSON`` interface as the rest of
    the pipeline (so a real backend and a test double are interchangeable). Provider unavailability is an
    honest refusal (None), never a fabricated value."""

    def __init__(self, select):
        self._select = select  # callable: (prompt: str) -> raw JSON str; may raise on provider failure

    def probe(self, surface: str, lemma: str | None) -> int | None:
        try:
            raw = self._select(build_numeral_probe_prompt(surface, lemma))
        except Exception:  # provider unavailable / transport error -> honest refusal, not a value
            return None
        return parse_numeral_probe_response(raw)


def _lemma_of(ev) -> str | None:
    """The token's lemma (top-variant mirror on TokenEvidence); None for OOV/unknown."""
    return getattr(ev, "lemma", None)


def _pos_of(ev) -> str | None:
    return getattr(ev, "pos", None)


def _surface_of(ev) -> str:
    span = getattr(ev, "span", None)
    if isinstance(span, tuple):
        return span[0] if span else ""
    return span or ""


# Unambiguous integer literals: bare digits ('52') or grouped thousands ('1 000', '1.000', '1 000 000').
# Decimals ('3,5'), ordinals ('42-й') and anything with letters are NOT cardinal literals -> no value.
_DIGIT_RE = re.compile(r"^\d{1,3}(?:[ \u00a0.,]\d{3})*$|^[0-9]+$")


def _digit_value(surface: str) -> int | None:
    """Read an unambiguous integer literal directly from the surface form (orthographic rule).
    Returns the integer, or None when the token is not a clean cardinal literal."""
    s = (surface or "").strip()
    if not _DIGIT_RE.match(s):
        return None
    try:
        return int(re.sub(r"[\s\u00a0.,]", "", s))
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
    """Cardinal extraction over a window of tokens ``evs[start:end]``.

    Deterministic first: a token in the seed table contributes its declared base value (POS-agnostic).
    Bounded fallback: a token NOT in the seed that is structurally a numeral candidate (POS == NUMR) is
    resolved by the bounded probe, subject to ``max_probes``. A maximal run of adjacent resolving tokens
    composes additively; the first non-resolving token terminates the run. Returns None when no numeral
    resolves in the window — an unknown value is never guessed.

    If ``sources`` is a list, each resolved component appends (origin, value) with origin in
    {'digits','table','probe'} so probe-derived values can be tagged as model judgment (M) downstream.
    """
    stop = len(evs) if end is None else min(end, len(evs))
    probes_used = 0
    cache: dict[int, tuple | None] = {}

    def resolve(idx: int):
        """Return (value, origin) for a token, or None if it does not resolve to an integer.
        Memoized per index so the locate and compose phases never re-probe the same token."""
        nonlocal probes_used
        if idx in cache:
            return cache[idx]
        # Layer 1: unambiguous digit literal reads directly (no table, no model).
        digits = _digit_value(_surface_of(evs[idx]))
        if digits is not None:
            cache[idx] = (digits, "digits")
            return (digits, "digits")
        value = table.get(_lemma_of(evs[idx]))
        if value is not None:
            cache[idx] = (value, "table")
            return (value, "table")
        # bounded fallback: only structurally-numeral tokens (POS NUMR) and only within the call budget
        if probe is not None and _pos_of(evs[idx]) == "NUMR" and probes_used < max_probes:
            probes_used += 1
            probed = probe.probe(_surface_of(evs[idx]), _lemma_of(evs[idx]))
            if probed is not None:
                cache[idx] = (probed, "probe")
                return (probed, "probe")
        cache[idx] = None
        return None

    # locate the numeral expression (skip leading non-numeral tokens such as 'не менее' / 'минимум')
    j = start
    while j < stop and resolve(j) is None:
        j += 1
    total = 0
    k = j
    while k < stop:
        resolved = resolve(k)
        if resolved is None:
            break  # run ends at the first non-resolving token
        value, origin = resolved
        total += value
        if sources is not None:
            sources.append((origin, value))
        k += 1
    return total if k > j else None
