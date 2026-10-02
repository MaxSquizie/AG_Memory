# Slice 12.96 — Discourse and temporal refinement

## Live evidence

The v0.12.95 document run completed all 98 perception units with `0` runtime errors. The technical documents stayed fully green. Literary graph scores were:

- `house_by_pier_monolith`: `53/56` (`35/36` event extraction, `1/2` temporal, `14/15` causal, `3/3` negative)
- `belyaev_amphibian_mutiny`: `25/36`
- `old_observatory_monolith`: `45/61`

This means the remaining defects are graph/discourse semantics rather than LM Studio transport, morphology crashes, or parser resource limits.

## 1. Pronoun-only provisional refs are not antecedents

Structural control and coordination can copy an unresolved third-person pronoun into multiple source frames before the normal coreference pass. Those copies need a temporary identity so they remain correlated, but that identity is not evidence that the pronoun has already been grounded.

Before this slice, a temporary ref could make the resolver skip the pronoun entirely:

```text
Алексей ... . Отперев калитку, он толкнул её.
                              ^ E_TMP
```

The resolver now first inspects all local entity refs. A ref used exclusively by third-person personal-pronoun mentions is reopened (`entity_ref=None`) before antecedent search. A ref also present on a non-pronominal mention is preserved as a genuine local binding. The regular source-only coreference algorithm then resolves the pronoun.

This is a representation invariant, not a name-specific rule.

## 2. Cross-turn discourse salience

The live `house_by_pier` failure showed:

```text
Марина ... . Бумага ... . печь ... . Она отодвинула письма ...
```

The old cache selected the latest feminine subject and therefore anchored `она` to `печь`. Recency alone is too weak for narrative continuity.

The new salience rule is bounded and morphology-based:

1. gather source-grounded SUBJECT candidates for each nominative pronoun signature;
2. determine whether the source nominal has a proper-name reading (`Name|Surn|Patr`) whose score is at least as strong as the best common-noun competitor;
3. if exactly one named ref exists, keep it as the anchor;
4. if several distinct named refs exist, clear the anchor;
5. otherwise use the latest source position, retaining the previous ambiguity-on-tie behavior.

This does **not** introduce a general `animate > inanimate` preference. Thus ordinary discourse such as `Лампа погасла. Точка появилась. Она ...` still resolves by recency when no named subject exists.

## 3. Clause relations target predicate evidence

The live source:

```text
Бумага в письмах намокла, потому что вода просочилась в коробку.
```

contained both the real event `намокнуть` and a structural nominal-attachment helper materialized from `в письмах`. The helper inherited the host parse span, so span-start matching could incorrectly select it as the main clause situation.

`primary_locals()` now matches the assertion predicate's own `EvidenceSpan` to the explicit clause predicate-head token. Structural helpers can share a host region without becoming the target of CAUSE/FOLLOW.

Expected canonical relation:

```text
просочиться --CAUSE--> намокнуть
```

## 4. Postnominal possessive morphology

The live old-observatory unit with:

```text
рама ... то дрожала, то снова замирала
```

failed before semantics because `то` exposed an `ADJF Anph Apro Subx` alternative. The older possessive test accepted `Subx` as enough evidence and incorrectly swallowed the token into the preceding NP.

Current pymorphy possessive-anaphor readings such as indeclinable `его/её/их` expose the stronger `Anph+Apro+Fixd` signature. v0.12.96 requires that explicit combination. `Subx` alone is no longer a possessive signal.

No surface-word list was added.

## 5. Serial perfective FOLLOW recovery

The frame graph is intentionally conservative. Literary sentences can express source-order event sequences without placing every pair in an explicit coordination group, for example after a detached gerund or across sibling clauses:

```text
Алексей снял чехол, подняв облачко пыли, и поставил лампу.
Вера узнала знак деда и закрыла глаза.
Вера собрала письма, унесла их и положила в ящик.
```

`EventNormalizer` now considers consecutive asserted, finite, perfective, top-level events inside one sentence. It adds `FOLLOW(A,B)` only when:

- an explicit additive `и`/`да` occurs between the event heads; or
- a comma separates them and both events have exactly the same SUBJECT identity.

The rule rejects adversative/disjunctive coordination (`но`, `однако`, `а`, `или`, `либо`), semicolons, subordinate/relative/quoted clauses, and non-perfective finite events.

The rule is temporal only. Source order does not prove causality. If the pair shares a participant, a runtime `CAUSAL_CANDIDATE` may be emitted, but canonical `CAUSE` still requires the existing semantic promotion mechanism.

## 6. Oracle corrections

Two old-observatory expectations were underspecified or surface-oriented:

- `see_letters` matched only predicate+subject and therefore had two valid `увидеть` candidates (letters and later smoke). It now requires structured OBJECT `пачка --GENITIVE_DEP--> письмо`.
- `close_eyes` expected surface `глаза`; canonical AH stores lemma `глаз` with `grammatical_number=plur`. The oracle now checks that canonical structure.

These changes make the oracle more precise; they do not forgive missing facts.

## Deferred deliberately

Belyaev still exposes a distinct proposition-content problem in `Зурита увидел, что ... приближалась подводная лодка`. The child event `лодка приближалась` is asserted content of perception, but forcing `лодка` into matrix OBJECT is not generally correct. This slice does not falsify the memory model merely to satisfy that oracle. A later slice should represent proposition/content links explicitly and then revise that literary expectation accordingly.

Likewise, descriptive re-mention identity (`матрос ... оглушенный матрос`) should be resolved before promoting the remaining implicit narrative CAUSE links.

## Verification

```text
pytest -q
577 passed, 22 subtests passed

python -m compileall -q src tests
compileall OK
```
