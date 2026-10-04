# -*- coding: utf-8 -*-
"""Tag source (V7 §6.2/§15): pymorphy3 (+ optional bounded LLM probe) -> tagged tokens for clause detection.

This is the production half of the *tagged path* in :mod:`ah.formalizer.clause_detection`. It turns raw text into
``list[Token]`` whose ``pos`` carries a subordination/relative label, so ``detect_clauses`` can derive paired clause
boundaries from **morphological categories** (the permitted structural side of the two-tier invariant) rather than from
per-word lexical rules.

Grounded in observed pymorphy3 behavior:
* ``если / хотя / чтобы / дабы`` parse as CONJ and are unambiguous subordinators -> auto-labeled ``CONJ_SUB``.
* ``когда / пока`` have a higher-ranked non-conjunction parse (ADVB) and are genuinely ambiguous (subordinator vs adverb);
  they are labeled ``CONJ_SUB`` **only** when an injected bounded LLM probe confirms subordinateness, else left as content
  (honest incompleteness — never guessed).
* Coordinating conjunctions (``и / а / но``) parse as CONJ too but are NOT in the declared set -> passed through as plain
  ``CONJ`` and therefore do **not** open a clause.
* Relative pronouns: an ADJF parse carrying the ``Subx`` grameme with a ``котор-`` lemma (e.g. ``который/которая``) is
  labeled ``RELPRON`` — a pure morph-category -> syntax decision.

The optional ``subord_probe(word) -> bool`` is the bounded LLM escape hatch for ambiguous conjunctions; results are cached
so each word is probed at most once per source (deterministic, no repeated calls). Punctuation tokens are preserved as
separate untagged tokens because :func:`detect_clauses` uses them as clause-closing delimiters.
"""

from __future__ import annotations

import re

from ah.formalizer.clause_detection import Token


# --- Declared structural resources (corpus-testable, NOT per-example) -------------------------------

#: Unambiguous subordinating conjunctions: auto-labeled CONJ_SUB when a CONJ/ADVB parse exists.
AUTO_SUBORDINATORS = frozenset({"если", "хотя", "чтобы", "дабы"})

#: Ambiguous subordinators (also read as adverbs): labeled CONJ_SUB only via the bounded LLM probe, else content.
AMBIGUOUS_SUBORDINATORS = frozenset({"когда", "пока"})

_REL_STEM = "котор"

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+|[^\sA-Za-zА-Яа-яЁё]+")
_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+$")


def tokenize(text: str) -> list[str]:
    """Whitespace tokenization that keeps words and punctuation as separate tokens (punct drives clause delimiters)."""
    return _WORD_RE.findall(text)


class TagSource:
    """Produce tagged :class:`Token` sequences from raw text via pymorphy3 (+ optional LLM probe).

    ``morph`` is any object with a ``parse(word) -> [Parse]`` method (a pymorphy3 ``MorphAnalyzer`` by default); inject a
    stub in tests. ``subord_probe`` is an optional ``word -> bool`` deciding subordinateness for ambiguous conjunctions.
    """

    def __init__(self, morph=None, subord_probe=None):
        if morph is None:
            from pymorphy3 import MorphAnalyzer
            morph = MorphAnalyzer()
        self._morph = morph
        self._probe = subord_probe
        self._cache: dict[str, str | None] = {}

    def _parses(self, word: str):
        try:
            return list(self._morph.parse(word))
        except Exception:  # pragma: no cover - defensive: a bad token must not break tagging
            return []

    def label(self, word: str) -> str | None:
        """Assign a subordination/relative label (or a coarse content POS) to one word. Cached per word."""
        if word in self._cache:
            return self._cache[word]
        parses = self._parses(word)
        low = word.lower()

        lab: str | None = None
        # (1) Relative pronoun: ADJF + Subx grameme + который-lemma  (morph category -> syntax).
        if any(p.tag.POS == "ADJF" and "Subx" in p.tag.grammemes
               and (p.normal_form or "").lower().startswith(_REL_STEM) for p in parses):
            lab = "RELPRON"
        # (2) Unambiguous subordinating conjunction, gated by a CONJ/ADVB parse existing.
        elif low in AUTO_SUBORDINATORS and any(p.tag.POS in ("CONJ", "ADVB") for p in parses):
            lab = "CONJ_SUB"
        # (3) Any other conjunction (ambiguous subordinators like когда/пока, complementizers like что,
        #     coordinators like и/а/но): resolved ONLY via the bounded LLM probe; without a probe it stays
        #     content (honest incompleteness — never guessed).
        elif any(p.tag.POS == "CONJ" for p in parses) and self._probe is not None:
            lab = "CONJ_SUB" if self._probe(word) else None

        if lab is None:
            # Pass through the top parse's coarse POS so downstream can use it; non-opener labels are ignored by detect_clauses.
            top = max(parses, key=lambda p: p.score) if parses else None
            # str() coerces pymorphy3's TypedGrammeme (a str *subclass* with custom __eq__) to a plain str.
            lab = (str(top.tag.POS) if top is not None and top.tag.POS else None)
        # pymorphy3 POS is a TypedGrammeme (custom __eq__/__ne__); normalize to a plain str for downstream string logic.
        if lab is not None and not isinstance(lab, str):
            lab = str(lab)

        self._cache[word] = lab
        return lab

    def tag(self, text: str) -> list[Token]:
        """Tag a full sentence into :class:`Token` sequence (words labeled; punctuation kept as untagged delimiters)."""
        out: list[Token] = []
        for tok in tokenize(text):
            if _LETTER_RE.match(tok):
                out.append(Token(tok, self.label(tok)))
            else:
                out.append(Token(tok, None))   # punctuation / other -> clause delimiter, no tag
        return out

    def detect(self, text: str):
        """Convenience: tagged tokens -> :class:`~ah.formalizer.clause_detection.ClauseStructure`."""
        from ah.formalizer.clause_detection import detect_clauses
        return detect_clauses(self.tag(text))


__all__ = ["TagSource", "tokenize", "AUTO_SUBORDINATORS", "AMBIGUOUS_SUBORDINATORS"]
