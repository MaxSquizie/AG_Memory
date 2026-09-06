# Slice 12.97 — Proposition content and local narrative causality

## Live evidence

The v0.12.96 document run is runtime-stable:

```text
Paragraph semantic: 98/98
Runtime errors:      0
Document acceptance: 4/6
```

Four documents are fully green, including the long `house_by_pier_monolith` at `56/56`.
The two remaining documents are:

```text
belyaev_amphibian_mutiny  25/36
old_observatory_monolith  59/61
```

The generic `summary.txt` reports the paragraph-level semantic verdict (`98/98`), while
`document_summary.txt` is the authoritative document-graph verdict (`4/6`).  The remaining
failures are therefore graph semantics, not runtime/parser transport failures.

## 1. Subordinate proposition content is an N actant

The Belyaev unit

```text
Зурита увидел, что ... приближалась подводная лодка.
```

already produced the child world event `приближаться(лодка)`, but the matrix
`увидеть(Зурита, ...)` had no OBJECT.  The previous orphan-subordinate refinement could
only ask whether the child SUBJECT should also become the matrix OBJECT.  That is not the
right semantic model here: Zurita sees *that the boat is approaching*.

AH already supports a hypernode as an actant of another hypernode.  v0.12.97 therefore
uses the existing `candidate_ref` path:

```text
N_APPROACH
└── SUBJECT -> m_SUBMARINE

N_SEE
├── SUBJECT -> m_ZURITA
└── OBJECT  -> N_APPROACH
```

Python still narrows the source to the exact orphaned connector shape, one matrix frame
with a free OBJECT and one nearest asserted finite child.  One tiny source-only probe then
chooses only among:

```text
EVENT_CONTENT
DIRECT_SUBJECT_OBJECT
NO_LINK
UNCLEAR
```

The model never sees canonical UIDs and never writes AH.  `EVENT_CONTENT` creates a
runtime `ActantCandidate(OBJECT, candidate_ref=child.local_id)`; Integration resolves it
through the ordinary dependency order and canonical write boundary.

The Belyaev oracle was corrected accordingly.  It now checks the child approach event
independently (including `лодка --NOMINAL_MODIFIER--> подводный`) and checks that
`zurita_see_submarine.OBJECT` is that fact.  This is a stricter architectural expectation,
not a weakened match.

## 2. Local causal review no longer requires one specific role transition

The unit

```text
Матрос ухватил его за ногу,
но Зурита ... ударил его по голове,
и оглушенный матрос упал на палубу.
```

contained all three events and a temporal `FOLLOW(ударить, упасть)`, but no CAUSE.
The old semantic promotion gate required only this shape:

```text
OBJECT/RECIPIENT(A) == SUBJECT(B)
```

That misses two common narrative forms:

```text
SUBJECT(A) == OBJECT(B)        # the first actor becomes the target of the reaction

ударил его -> оглушенный матрос упал
                              # descriptive re-mention identity is not converged yet
```

The gate remains deliberately sparse.  A same-sentence `CAUSAL_CANDIDATE` is sent to the
tiny `ENTAILED | NOT_ENTAILED | UNCLEAR` probe only when either:

1. canonical/source-local identity already shows a SUBJECT↔OBJECT/RECIPIENT role transition; or
2. `EventNormalizer` identifies the target SUBJECT as a passive-participle result description.

Ordinary same-subject serial narration such as `написал письмо и отправил его` or
`взяла книгу, открыла её и прочитала` does not trigger a new causal model call.  Source
order and FOLLOW never become CAUSE by themselves.

For serial perfective pairs, the normalizer still emits its causal hypothesis only when
there is participant continuity, plus the new passive-result structural case.  The hint
remains runtime-only until the semantic entailment probe returns `ENTAILED`.

## 3. Pre-predicate locative PP normalization

The old-observatory failures both came from one unit:

```text
За окнами усиливался ветер;
рама в дальней комнате то дрожала, то снова замирала.
Поскольку защёлка давно не держалась в пазу,
очередной порыв распахнул створку.
```

The parser had already recognized `усиливаться(ветер)`, but parsing the next clause reached
an attachment choice for `в дальней комнате`.  The model returned `UNCLEAR`, causing the
existing structural-clarification contract to preserve only the raw H turn; consequently
both the already parsed wind event and the later gust event were absent from C.

v0.12.97 adds one narrow deterministic normalization before the model attachment probe:

```text
NP + bare PREP + locative complement ... finite predicate
```

when the PP occurs on the pre-predicate side and exactly one adjacent nominal owner also
exists, the PP is represented as an event-level location.  This keeps the proposition
semantically usable without inventing an entity identity.  It does **not** apply to
post-predicate/object PPs.

The genuine instrumental ambiguity remains untouched and still requires clarification:

```text
Иван увидел Петра с биноклем.
                   ^ event tool OR modifier of Пётр
```

Thus the acceptance ambiguity boundary from the earlier slices is preserved.

## 4. What is deliberately not solved in this slice

The remaining Belyaev expectations are discourse relations whose endpoints occur in
different input turns, for example:

```text
sailors_attack        -> CAUSE  -> zurita_break_free
sailors_discuss       -> FOLLOW -> sailors_head_hatch
zurita_see_submarine  -> CAUSE  -> zurita_cry_help
submarine_approach    -> CAUSE  -> sailors_stop
sailors_understand_escape -> CAUSE -> sailors_lower_boats
```

`PerceptionResult.relations` currently has turn-local local-id endpoints by design.  Adding
cross-turn relations by scanning the whole AH or by acceptance-specific post-processing
would violate the architecture.  The next slice should introduce a bounded runtime
discourse-relation candidate mechanism over recent/activated canonical events, followed by
a tiny source-grounded semantic decision and a canonical Integration/AH-Core write.

This is kept separate from v0.12.97 so the new contract can be tested independently rather
than hidden inside parser heuristics.

## Verification

```text
python -m compileall -q src tests
pytest -q
579 passed, 22 subtests passed
```
