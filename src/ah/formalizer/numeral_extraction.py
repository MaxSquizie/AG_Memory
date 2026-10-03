# -*- coding: utf-8 -*-
"""WP3.2 — Cardinal numeral extraction (declared language resource + declared composition rule).

Empirical basis (pymorphy3/OpenCorpora): Russian numerals have NO reliable morphological value signal —
POS is inconsistent (2-9/ten/twenty parse as NUMR, but сто/тысяча/миллион/ноль parse as NOUN and один
as ADJF) and no NUMB* grammeme is exposed. Therefore the integer VALUE of a numeral cannot be read from
the tagset; it comes from a DECLARED LANGUAGE RESOURCE (lemma -> base value), which the project invariant
sanctions ("lexical-semantic mappings ... via language resources").

Two declared, corpus-testable pieces — no per-word logic in code:
  * NUMERAL_LEXICON_V1  : the resource. A single numeral token maps to its base value directly.
  * additive composition: a maximal run of ADJACENT numeral tokens composes by SUMMING their base values
    (standard Russian cardinal composition: 'двадцать три' = 20+3, 'сто пять' = 100+5).

Honest boundary: an unknown lemma contributes nothing and terminates the run — extraction returns None
rather than guessing a value. Ordinals ('третий', ADJF) and fuzzy quantifiers ('несколько','много', ADVB)
are NOT in the resource, so they are not treated as cardinals here (they are different constructs).
"""

from __future__ import annotations

# Declared language resource [numeral_lexicon_v1]: Russian cardinal lemmas -> base value.
# Standard forms 0..1000; exotic/collective numerals are intentionally out of coverage (-> None).
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


def _lemma_of(ev) -> str | None:
    """The token's lemma (top-variant mirror on TokenEvidence); None for OOV/unknown."""
    return getattr(ev, "lemma", None)


def extract_cardinal_value(evs, start: int, end: int | None = None) -> int | None:
    """Declared cardinal extraction over a window of tokens ``evs[start:end]``.

    Skips leading non-numeral tokens up to the first known numeral, then composes a maximal run of
    adjacent numeral tokens by summing their declared base values (additive composition). Returns None
    when no known numeral lies in the window — an unknown lemma is never assigned a value.
    """
    stop = len(evs) if end is None else min(end, len(evs))
    j = start
    while j < stop and NUMERAL_LEXICON_V1.get(_lemma_of(evs[j])) is None:
        j += 1  # advance to the numeral expression (e.g. past 'не менее' / 'минимум')
    total = 0
    k = j
    while k < stop:
        value = NUMERAL_LEXICON_V1.get(_lemma_of(evs[k]))
        if value is None:
            break  # run ends at the first non-numeral token
        total += value
        k += 1
    return total if k > j else None
