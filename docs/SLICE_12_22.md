# Slice 12.22 — structural relation normalization and stronger Perception narrowing

This slice continues the architecture-first correction from 12.20/12.21. It does
not broaden Integration into an NLP parser and does not introduce T valency evolution.

## 1. One inter-situation meaning, one canonical representation

`Архитектура_v3` separates predicate facts (`N`) from typed structural relations
(`L`). Therefore a causal or directional temporal clause must not be encoded twice:

```text
bad:
N_EFFECT.CAUSE = N_CAUSE
N_CAUSE --CAUSE--> N_EFFECT

canonical:
N_CAUSE --CAUSE--> N_EFFECT
```

Likewise, after/before clauses represented by `FOLLOW` no longer also store the
subordinate situation as `N.TIME`.

Perception still uses its temporary candidate_ref actant while determining clause
structure. After `SituationRelationCandidate` construction it removes only the
redundant situation-valued `CAUSE/TIME` candidate_ref. Entity-valued roles such as a
concrete date, location or reason entity are unchanged.

Candidate Validation rejects externally supplied duplicate CAUSE/FOLLOW encodings, so
the invariant also holds for non-adaptive Perception producers.

## 2. Hierarchical TemplateCandidate proposal

The 12.20 flat probe asked a weak LLM to choose one role from almost the whole role
ontology plus `0 = complete`. In the real acceptance run it answered `0` for every
hidden-role request.

12.22 keeps the architecture's required `LLM TemplateCandidate` step but makes each
semantic decision atomic:

```text
unknown predicate
  ↓
observed roles
  ↓
[0/1] is any additional lexically selected role omitted?
  ↓ yes
choose role family
  ↓
choose one role inside that family
  ↓
repeat until complete
  ↓
deterministic TemplateCandidate validation
```

The prompt distinguishes lexical government/valency from incidental event context.
TIME/LOCATION/CAUSE/PURPOSE may be proposed only when that predicate sense actually
selects such a complement.

Existing canonical T behavior is unchanged:

```text
FilledRoles(N) ⊆ Roles(T)
```

and later widening remains explicit failure because `T valency evolution` is still
`[DEFER]`.

## 3. Lexical identity: dominant proper-name paradigms

`stable_normal_form` still requires consensus for competing material analyses by
default. A narrow dominance rule now handles dictionary ambiguity such as:

```text
Петру:
  Пётр / datv  0.666...
  Петра / accs 0.333...
```

The dominant lexical identity is `Пётр`, so Text Sensory and semantic actant lookup
reuse one S/entity path for `Пётр / Петра / Петру`.

Equal-score lexical ambiguity remains unresolved:

```text
пришли -> прислать 0.5
пришли -> прийти   0.5
```

and later grammatical constraints still decide it.

Materiality is evaluated before optional POS filtering, preventing tiny dictionary
readings from normalizing an overwhelmingly adverbial token (for example `Потом`)
as a noun.

## 4. Conservative discourse coreference

Canonical entity choice still belongs to deterministic resolution. LLM antecedent
selection is not reintroduced.

For an explicit continuation marker (`Потом`, `Затем`, `Тогда`, `Далее`), Perception
first limits antecedents to the immediately preceding sentence and may prefer the
same grammatical role only when exactly one such antecedent exists there. This
resolves the benchmark chain:

```text
Сергей положил ключ на стол. Потом он взял его.
SUBJECT -> previous SUBJECT (Сергей)
OBJECT  -> previous OBJECT  (ключ)
```

Without an explicit continuation marker the resolver preserves competing readings as
runtime alternatives; genuine cases such as `Анна увидела Марию. Она улыбнулась.`
therefore remain ambiguous and enter the 12.21 clarification lifecycle.

Coreference morphology now uses only materially competitive analyses, so rare parses
cannot manufacture antecedent candidates.

## 5. Spatial adverbs

Lexical spatial adverbs are deterministic linguistic evidence. Forms such as `дома`,
`здесь`, `там`, `внутри`, `снаружи`, `впереди`, `позади`, etc. narrow directly to
`LOCATION` when an adverbial morphology reading is structurally available.

This fixes:

```text
Иван остался дома.
→ STAY(SUBJECT=Иван, LOCATION=дом)
```

without moving role correction into Integration and without an LLM guess.

## 6. PP attachment remains explicitly unresolved

`Иван увидел Петра с биноклем` still has two readings: the PP may modify the seeing
event or the object noun phrase. The current canonical contract has no noun-modifier
relation capable of representing the second reading faithfully. Encoding it as
`SEE.TOOL`, `SEE.AUXILLIARY` or `AND(Пётр, бинокль)` would silently invent semantics.

Therefore 12.22 deliberately preserves the architecture invariant:

```text
VALID_GRAPH or EXPLICIT_AMBIGUITY / EXPLICIT_ERROR
```

and leaves this PP case as explicit Perception ambiguity until the architecture gains
a faithful nominal-modification representation or a proposition-level ambiguity
container.

Ignition and the 12.21 clarification mutation path are unchanged.
