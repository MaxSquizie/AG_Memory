# -*- coding: utf-8 -*-
"""Clause detection (V7 §6.2/§15): deterministic paired clause boundaries for IF and embedded propositions.

The normative contract: IF/IMPLIES domains require **paired** clause boundaries (§6.2 IMPLIES row, TD scope by the
declared pair), and embedded/hypothetical propositions need a matrix + subordinate split (§18 DR27 A37). Until this
exists, IF queries stay UNRESOLVED / QUERY_TARGET_UNBOUND (V7 §6.3) — they are never guessed.

**Two-tier invariant compliance.** Clause boundaries are derived from *morphological categories* (a subordinating
conjunction or a relative pronoun), i.e. "morph category -> syntactic decision" — the permitted structural side of the
invariant, declared here and corpus-testable. There is **no per-example lexical rule**:

* Tagged path (primary): a token opens a subordinate clause when its POS marks it as a subordinating conjunction or a
  relative pronoun. In production the tagger/LLM supplies these tags; detection is then a pure structural operation.
* Untagged fallback: a small, explicitly **declared** set of *unambiguous* subordinators (``если``, ``когда``, ``хотя``,
  ``пока``, ``чтобы``) plus the relative stem ``котор-``. This is a declared structural resource (analogous to the
  operator-algebra / numeral seed), not per-word hacks. The ambiguous complementizer ``что`` is deliberately **not** in
  the untagged set — without a tag it cannot be told from the pronoun, so it opens a clause only via its CONJ tag.

Two declared structural signals drive the split: (1) a subordinate **opener**, and (2) **clause-closing punctuation**
(.,;:!?) which terminates an open subordinate clause so that a following main fragment can begin (the «Если X, Y» shape).
Coverage is deliberately bounded (V7 finite-operations philosophy): unsupported shapes degrade to the whole span as one
clause rather than being mis-split. Pure module; no store/network/morphology access. Deterministic: same tokens -> same structure.
"""

from __future__ import annotations

from dataclasses import dataclass


# --- Declared structural resources (corpus-testable, NOT per-example) -------------------------------

#: POS labels that mark a subordinating conjunction / relative pronoun (tagged path). Matched case-insensitively;
#: any label containing "SUB" is also treated as subordinating so richer taggers plug in without code changes.
_SUBORDINATOR_POS = {"CONJ_SUB", "SUBORD", "RELPRON"}


def _is_subordinator_pos(pos: str | None) -> bool:
    if not pos:
        return False
    p = pos.upper()
    return p in _SUBORDINATOR_POS or "SUB" in p


#: Untagged fallback: unambiguous subordinators only. ``что`` is excluded (pronoun ambiguity without a tag).
DECLARED_SUBORDINATORS = frozenset({"если", "когда", "хотя", "пока", "чтобы"})

#: Relative-clause marker by stem (declared structural resource, not a lexical-semantic mapping).
_RELATIVE_STEM = "котор"

_PUNCT = frozenset(".,;:!?…")


# Clause opener relations.
MATRIX = None          # the main clause (no opener)
IF = "IF"             # conditional -> IMPLIES pair
COMPLEMENT = "COMPLEMENT"  # content/finite subordinate (чтобы, когда, хотя, пока, ...)
RELATIVE = "RELATIVE"      # relative clause attached to a preceding nominal


@dataclass(frozen=True)
class Token:
    text: str
    pos: str | None = None   # optional morphological tag; drives the tagged path


@dataclass(frozen=True)
class Clause:
    index: int
    start: int              # token offset (inclusive)
    end: int                # token offset (exclusive)
    text: str
    opener: str | None      # MATRIX(None) | IF | COMPLEMENT | RELATIVE


@dataclass(frozen=True)
class ClauseEdge:
    parent: int             # clause index the subordinate attaches to
    child: int             # subordinate clause index
    relation: str          # IF | COMPLEMENT | RELATIVE


@dataclass(frozen=True)
class ClauseStructure:
    clauses: tuple[Clause, ...]
    edges: tuple[ClauseEdge, ...] = ()

    @property
    def is_single(self) -> bool:
        return len(self.clauses) <= 1

    @property
    def matrix_index(self) -> int:
        for c in self.clauses:
            if c.opener is MATRIX:
                return c.index
        return 0

    def if_pairs(self) -> list[tuple[int, int]]:
        """Paired (antecedent, consequent) clause indices for IMPLIES / TD scope.

        A conditional subordinate is the antecedent; its consequent defaults to the matrix clause it attaches to.
        """
        return [(e.child, e.parent) for e in self.edges if e.relation == IF]


def _opener_kind(tok: Token) -> str | None:
    if _is_subordinator_pos(tok.pos):
        # A tagged relative pronoun is a RELATIVE opener; any other subordinating tag is COMPLEMENT/IF by form.
        if tok.pos and "REL" in tok.pos.upper():
            return RELATIVE
        low = tok.text.lower()
        return IF if low == "если" else COMPLEMENT
    low = tok.text.lower().strip(".,;:!?…")
    if low.startswith(_RELATIVE_STEM):
        return RELATIVE
    if low in DECLARED_SUBORDINATORS:
        return IF if low == "если" else COMPLEMENT
    return None


def _is_punct(tok: Token) -> bool:
    return tok.text.strip() in _PUNCT


def detect_clauses(tokens) -> ClauseStructure:
    """Split ``tokens`` (iterable of :class:`Token`) into a matrix clause + subordinate clauses with typed edges.

    Deterministic and pure. A single-clause input yields an empty edge set (honest: no IF/embedded structure — never
    guessed). Subordinate clauses attach to the nearest preceding main fragment, or to the matrix when they lead it.
    """
    toks = list(tokens)
    n = len(toks)
    if n == 0:
        return ClauseStructure(())

    opener_at: dict[int, str] = {}
    for i, tok in enumerate(toks):
        kind = _opener_kind(tok)
        if kind is not None:
            opener_at[i] = kind

    def span_text(a: int, b: int) -> str:
        return " ".join(t.text for t in toks[a:b]).strip()

    # No subordinate opener anywhere -> a single matrix clause (honest incompleteness, not a mis-split).
    if not opener_at:
        return ClauseStructure((Clause(0, 0, n, span_text(0, n), MATRIX),))

    blocks: list[tuple[int, int, str | None]] = []   # (start, end_exclusive, kind|None)
    i = 0
    while i < n:
        while i < n and _is_punct(toks[i]):              # skip separator punctuation before content
            i += 1
        if i >= n:
            break
        if i in opener_at:
            kind = opener_at[i]
            start = i
            j = i + 1
            while j < n and j not in opener_at:          # a comma/period closes the subordinate (not RELATIVE)
                if _is_punct(toks[j]) and kind != RELATIVE:
                    break
                j += 1
            blocks.append((start, j, kind))              # exclude closing punct / stop at next opener
            i = j
        else:
            start = i
            j = i + 1
            while j < n and j not in opener_at and not _is_punct(toks[j]):
                j += 1
            blocks.append((start, j, None))              # main fragment (ends at next opener or punct)
            i = j

    clauses: list[Clause] = []
    edges: list[ClauseEdge] = []
    for start, end, kind in blocks:
        if span_text(start, end) == "":
            continue
        idx = len(clauses)
        clauses.append(Clause(idx, start, end, span_text(start, end), kind))

    main_indices = [c.index for c in clauses if c.opener is None]
    matrix = max(main_indices) if main_indices else (clauses[-1].index if clauses else 0)
    for c in clauses:
        if c.opener is None:
            continue
        preceding_mains = [m.index for m in clauses if m.opener is None and m.end <= c.start]
        parent = max(preceding_mains) if preceding_mains else matrix
        edges.append(ClauseEdge(parent, c.index, c.opener))

    return ClauseStructure(tuple(clauses), tuple(edges))


def paired_boundaries(structure: ClauseStructure) -> list[tuple[int, int]]:
    """The paired clause boundaries IMPLIES / TD scope consume (antecedent, consequent). Empty when single-clause."""
    if structure.is_single:
        return []
    return structure.if_pairs()


__all__ = [
    "Token", "Clause", "ClauseEdge", "ClauseStructure",
    "MATRIX", "IF", "COMPLEMENT", "RELATIVE",
    "DECLARED_SUBORDINATORS", "detect_clauses", "paired_boundaries",
]
