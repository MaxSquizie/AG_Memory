from __future__ import annotations

from ah.config import InferenceSettings
from ah.conflict import ConflictEngine
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    FormulaGoal,
    GoalSpec,
    InferenceEngine,
    InferenceQuery,
    InferenceSchema,
    InferenceSchemaRegistry,
    LogicalStatus,
    RelationGoal,
    StopReason,
)
from ah.model import ActantRole, Domain, Property, Ref


def _entity(core: AHCore, name: str) -> Ref:
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _assert_unary(core: AHCore, predicate: str, subject: Ref) -> Ref:
    symbol = core.ensure_abstract_symbol(predicate)
    template = core.add_template(Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT,))
    node, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: subject},
        0.4,
        count_occurrence=True,
    )
    return core.ref(node.uid)


def _assert_formula_occurrence(core: AHCore, formula_ref: Ref) -> None:
    speaker = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")}
    )
    predicate = core.ensure_abstract_symbol("утверждать")
    template = core.add_template(
        Domain.H,
        core.ref(predicate.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    core.add_hypernode(
        Domain.H,
        core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(speaker.uid), ActantRole.OBJECT: formula_ref},
        0.3,
        meta={"event_instance": True},
        deduplicate=False,
    )


def _solve_formula(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def _solve_relation(engine: InferenceEngine, relation: str, source: Ref, target: Ref):
    return engine.solve(
        InferenceQuery(GoalSpec(RelationGoal(relation, source, target)))
    )


def test_or_elimination_requires_explicit_refutation_of_every_other_branch() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    x = _entity(core, "объект")
    a = _assert_unary(core, "режим A", x)
    b = _assert_unary(core, "режим B", x)

    # The disjunct atoms are scoped patterns, not independent factual premises.
    from dataclasses import replace

    for ref in (a, b):
        node = core.store.get_hypernode(ref.uid)
        core.edit_element(
            Domain.C,
            replace(
                node,
                meta={**dict(node.meta), "semantic_scope": "DISJUNCTIVE", "occurrence_count": 0},
            ),
        )

    or_g, _ = core.ensure_function(Domain.C, "OR", (a, b))
    or_ref = core.ref(or_g.uid)
    _assert_formula_occurrence(core, or_ref)

    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    assert _solve_formula(engine, b).status is LogicalStatus.UNKNOWN

    not_a, _ = core.ensure_function(Domain.C, "NOT", (a,))
    not_a_ref = core.ref(not_a.uid)
    _assert_formula_occurrence(core, not_a_ref)

    result = _solve_formula(engine, b)
    assert result.status is LogicalStatus.PROVED
    assert result.stop_reason is StopReason.GOAL_SATISFIED
    assert result.proof_support[0].rule_id == "OR_ELIM"
    assert or_ref.uid in {ref.uid for ref in result.premise_refs}
    assert not_a_ref.uid in {ref.uid for ref in result.premise_refs}


def test_or_elimination_does_not_treat_unknown_as_false() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    x = _entity(core, "объект")
    a = _assert_unary(core, "режим A", x)
    b = _assert_unary(core, "режим B", x)
    c = _assert_unary(core, "режим C", x)

    from dataclasses import replace

    for ref in (a, b, c):
        node = core.store.get_hypernode(ref.uid)
        core.edit_element(
            Domain.C,
            replace(
                node,
                meta={**dict(node.meta), "semantic_scope": "DISJUNCTIVE", "occurrence_count": 0},
            ),
        )

    or_g, _ = core.ensure_function(Domain.C, "OR", (a, b, c))
    _assert_formula_occurrence(core, core.ref(or_g.uid))
    not_a, _ = core.ensure_function(Domain.C, "NOT", (a,))
    _assert_formula_occurrence(core, core.ref(not_a.uid))

    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    # C is still UNKNOWN, therefore B cannot be selected by closed-world elimination.
    assert _solve_formula(engine, b).status is LogicalStatus.UNKNOWN


def test_relation_schema_executes_symmetric_reflexive_irreflexive_and_inverse() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    a = _entity(core, "A")
    b = _entity(core, "B")
    core.add_link("OVERLAP", b, a, 0.4)
    core.add_link("PARENT_OF", a, b, 0.4)

    registry = InferenceSchemaRegistry(
        (
            InferenceSchema("OVERLAP", symmetric=True),
            InferenceSchema("SAME_REGION", reflexive=True),
            InferenceSchema("BEFORE", irreflexive=True),
            InferenceSchema("PARENT_OF", inverse_of="CHILD_OF"),
        )
    )
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=8, max_expanded_states=128),
        schema_registry=registry,
    )

    symmetric = _solve_relation(engine, "OVERLAP", a, b)
    assert symmetric.status is LogicalStatus.PROVED
    assert symmetric.proof_support[0].rule_id == "SYMMETRY"

    reflexive = _solve_relation(engine, "SAME_REGION", a, a)
    assert reflexive.status is LogicalStatus.PROVED
    assert reflexive.proof_support[0].rule_id == "REFLEXIVE"

    irreflexive = _solve_relation(engine, "BEFORE", a, a)
    assert irreflexive.status is LogicalStatus.DISPROVED
    assert irreflexive.stop_reason is StopReason.GOAL_REFUTED
    assert irreflexive.proof_support[0].rule_id == "IRREFLEXIVE"

    inverse = _solve_relation(engine, "CHILD_OF", b, a)
    assert inverse.status is LogicalStatus.PROVED
    assert inverse.proof_support[0].rule_id == "INVERSE_OF"


def test_schema_mutual_exclusion_creates_positive_positive_conflict_only_on_key_match() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    subject = _entity(core, "дверь")
    other_subject = _entity(core, "окно")

    open_symbol = core.ensure_abstract_symbol("быть открытым")
    closed_symbol = core.ensure_abstract_symbol("быть закрытым")
    open_template = core.add_template(
        Domain.C, core.ref(open_symbol.uid), (ActantRole.SUBJECT,)
    )
    closed_template = core.add_template(
        Domain.C, core.ref(closed_symbol.uid), (ActantRole.SUBJECT,)
    )

    def add(template, who):
        node, _ = core.add_hypernode(
            Domain.C,
            core.ref(template.uid),
            {ActantRole.SUBJECT: who},
            0.4,
            count_occurrence=True,
        )
        return core.ref(node.uid)

    opened = add(open_template, subject)
    closed = add(closed_template, subject)
    unrelated_closed = add(closed_template, other_subject)

    registry = InferenceSchemaRegistry(
        (
            InferenceSchema(
                open_template.uid,
                mutually_exclusive_with=(closed_template.uid,),
                exclusion_key_roles=(ActantRole.SUBJECT,),
            ),
        )
    )
    conflicts = ConflictEngine(core, registry)
    records = conflicts.register_asserted_roots((opened, closed, unrelated_closed))

    assert len(records) == 1
    assert records[0].kind == "MUTUAL_EXCLUSION"
    assert set(records[0].members) == {opened, closed}
    assert conflicts.is_conflicted(opened)
    assert conflicts.is_conflicted(closed)
    assert not conflicts.is_conflicted(unrelated_closed)


def test_mutual_exclusion_is_conservative_without_explicit_key_roles() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    subject = _entity(core, "дверь")
    left_symbol = core.ensure_abstract_symbol("состояние A")
    right_symbol = core.ensure_abstract_symbol("состояние B")
    left_template = core.add_template(Domain.C, core.ref(left_symbol.uid), (ActantRole.SUBJECT,))
    right_template = core.add_template(Domain.C, core.ref(right_symbol.uid), (ActantRole.SUBJECT,))
    left, _ = core.add_hypernode(
        Domain.C, core.ref(left_template.uid), {ActantRole.SUBJECT: subject}, 0.4, count_occurrence=True
    )
    right, _ = core.add_hypernode(
        Domain.C, core.ref(right_template.uid), {ActantRole.SUBJECT: subject}, 0.4, count_occurrence=True
    )
    registry = InferenceSchemaRegistry(
        (InferenceSchema(left_template.uid, mutually_exclusive_with=(right_template.uid,)),)
    )
    engine = ConflictEngine(core, registry)
    assert engine.register_asserted_roots((core.ref(left.uid), core.ref(right.uid))) == ()
