from __future__ import annotations

import pytest

from ah.agent import InteractionContext
from ah.config import InferenceSettings, PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.inference import FormulaGoal, GoalSpec, InferenceEngine, InferenceQuery, LogicalStatus
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.errors import UnresolvedDiscourseReferenceError
from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Property, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QuantifierCandidate,
    QuantifierKind,
    TemplateCandidate,
)
from ah.perception.morphology import MorphInfo


class _Morphology:
    """Small deterministic grammar for the cross-turn existential acceptance."""

    _VERBS = {
        "вошел": ("войти", "masc"),
        "сел": ("сесть", "masc"),
        "вышел": ("выйти", "masc"),
        "увидел": ("увидеть", "masc"),
        "улыбнулся": ("улыбнуться", "masc"),
    }

    def analyze_all(self, word: str):
        normalized = word.casefold().replace("ё", "е")
        if normalized == "он":
            return (
                MorphInfo(
                    "он",
                    "NPRO",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    grammemes=frozenset({"NPRO", "3per"}),
                    score=1.0,
                ),
            )
        if normalized in {"кто-то", "кто-нибудь", "кто-либо"}:
            return (
                MorphInfo(
                    normalized,
                    "NPRO",
                    case="nomn",
                    number="sing",
                    grammemes=frozenset({"NPRO"}),
                    score=1.0,
                ),
            )
        if normalized == "иван":
            return (
                MorphInfo(
                    "иван",
                    "NOUN",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    grammemes=frozenset({"Name"}),
                    score=1.0,
                ),
            )
        if normalized in self._VERBS:
            lemma, gender = self._VERBS[normalized]
            return (
                MorphInfo(
                    lemma,
                    "VERB",
                    number="sing",
                    gender=gender,
                    mood="indc",
                    grammemes=frozenset({"past"}),
                    score=1.0,
                ),
            )
        return ()

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def _env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Агент", "str")}, uid="M_SELF"
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")}, uid="M_USER"
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid)
    )
    service = IntegrationService(
        core,
        IntegrationConfig(0.4, 0.3, 0.2),
        discourse_morphology=_Morphology(),
    )
    return core, context, service


def _unary(
    local_id: str,
    surface: str,
    lemma: str,
    mention: str,
    *,
    entity_ref: str | None = None,
    quantified: bool = False,
):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            surface,
            lemma,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention=mention,
                normalized_hint=mention.casefold(),
                entity_ref=entity_ref,
                quantifier=(
                    QuantifierCandidate(QuantifierKind.EXISTS, mention)
                    if quantified
                    else None
                ),
            ),
        ),
    )


def _binary(
    local_id: str,
    surface: str,
    lemma: str,
    subject: ActantCandidate,
    obj: ActantCandidate,
):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            surface,
            lemma,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (subject, obj),
    )


def _solve(core: AHCore, ref):
    engine = InferenceEngine(core, InferenceSettings(max_depth=12, max_expanded_states=512))
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def test_cross_turn_pronoun_extends_same_existential_scope_without_fake_entity() -> None:
    core, context, service = _env()
    first = service.integrate_external(
        PerceptionResult(
            "Кто-то вошёл.",
            assertions=(
                _unary(
                    "A1", "вошёл", "войти", "Кто-то",
                    entity_ref="E1", quantified=True,
                ),
            ),
        ),
        context,
    )
    first_exists = first.existentials[0]
    assert first_exists.variable_ids == (0,)
    assert "он" in context.existential_pronoun_anchors
    assert "он" not in context.pronoun_refs

    second_plan = service.prepare_external_plan(
        PerceptionResult(
            "Он сел.",
            assertions=(_unary("A2", "сел", "сесть", "Он"),),
        ),
        context,
    )
    assert second_plan.candidate_ir.discourse_refs == ()
    assert len(second_plan.candidate_ir.existential_bindings) == 1
    binding = second_plan.candidate_ir.existential_bindings[0]
    assert binding.anchor_ref == first_exists.ref
    assert binding.anchor_member_refs == first_exists.member_refs

    second = service.integrate_plan(second_plan, context)
    combined = second.existentials[0]
    assert combined.variable_ids == (0,)
    assert len(combined.member_refs) == 2
    assert first_exists.member_refs[0] in combined.member_refs
    assert combined.ref != first_exists.ref
    assert _solve(core, combined.ref).status is LogicalStatus.PROVED

    for member in combined.member_refs:
        subject = core.store.get_hypernode(member.uid).actants[ActantRole.SUBJECT]
        assert isinstance(subject, BoundVar) and subject.local_id == 0
    assert core.store.find_entities_by_name("он", Domain.C) == ()
    assert core.store.find_entities_by_name("кто-то", Domain.C) == ()

    latest = context.existential_pronoun_anchors["он"]
    assert latest.existential_ref == combined.ref
    assert latest.member_refs == combined.member_refs


def test_three_turn_existential_chain_accumulates_one_participant_scope() -> None:
    core, context, service = _env()
    first = service.integrate_external(
        PerceptionResult(
            "Кто-то вошёл.",
            assertions=(
                _unary(
                    "A1", "вошёл", "войти", "Кто-то",
                    entity_ref="E1", quantified=True,
                ),
            ),
        ),
        context,
    )
    second = service.integrate_external(
        PerceptionResult("Он сел.", assertions=(_unary("A2", "сел", "сесть", "Он"),)),
        context,
    )
    third = service.integrate_external(
        PerceptionResult(
            "Он улыбнулся.",
            assertions=(_unary("A3", "улыбнулся", "улыбнуться", "Он"),),
        ),
        context,
    )

    assert len(first.existentials[0].member_refs) == 1
    assert len(second.existentials[0].member_refs) == 2
    assert len(third.existentials[0].member_refs) == 3
    assert set(second.existentials[0].member_refs).issubset(set(third.existentials[0].member_refs))
    assert third.existentials[0].variable_ids == (0,)
    assert _solve(core, third.existentials[0].ref).status is LogicalStatus.PROVED


def test_two_same_signature_unknowns_do_not_create_arbitrary_cross_turn_anchor() -> None:
    _core, context, service = _env()
    service.integrate_external(
        PerceptionResult(
            "Кто-то вошёл. Кто-то вышел.",
            assertions=(
                _unary(
                    "A1", "вошёл", "войти", "Кто-то",
                    entity_ref="E1", quantified=True,
                ),
                _unary(
                    "A2", "вышел", "выйти", "Кто-то",
                    entity_ref="E2", quantified=True,
                ),
            ),
        ),
        context,
    )
    assert "он" not in context.existential_pronoun_anchors

    plan = service.prepare_external_plan(
        PerceptionResult("Он сел.", assertions=(_unary("A3", "сел", "сесть", "Он"),)),
        context,
    )
    assert len(plan.candidate_ir.discourse_refs) == 1
    with pytest.raises(UnresolvedDiscourseReferenceError):
        service.integrate_plan(plan, context)


def test_multi_variable_existential_is_not_guessed_as_cross_turn_person_anchor() -> None:
    _core, context, service = _env()
    commit = service.integrate_external(
        PerceptionResult(
            "Кто-то увидел что-то.",
            assertions=(
                _binary(
                    "A1",
                    "увидел",
                    "увидеть",
                    ActantCandidate(
                        ActantRole.SUBJECT,
                        mention="Кто-то",
                        entity_ref="E1",
                        quantifier=QuantifierCandidate(
                            QuantifierKind.EXISTS, "Кто-то"
                        ),
                    ),
                    ActantCandidate(
                        ActantRole.OBJECT,
                        mention="что-то",
                        entity_ref="E2",
                        quantifier=QuantifierCandidate(
                            QuantifierKind.EXISTS, "что-то"
                        ),
                    ),
                ),
            ),
        ),
        context,
    )
    assert commit.existentials[0].variable_ids == (0, 1)
    assert "он" not in context.existential_pronoun_anchors

    plan = service.prepare_external_plan(
        PerceptionResult("Он сел.", assertions=(_unary("A2", "сел", "сесть", "Он"),)),
        context,
    )
    assert len(plan.candidate_ir.discourse_refs) == 1


def test_named_subject_supersedes_older_existential_anchor() -> None:
    core, context, service = _env()
    service.integrate_external(
        PerceptionResult(
            "Кто-то вошёл.",
            assertions=(
                _unary(
                    "A1", "вошёл", "войти", "Кто-то",
                    entity_ref="E1", quantified=True,
                ),
            ),
        ),
        context,
    )
    assert "он" in context.existential_pronoun_anchors

    named = service.integrate_external(
        PerceptionResult(
            "Иван сел.",
            assertions=(_unary("A2", "сел", "сесть", "Иван", entity_ref="E2"),),
        ),
        context,
    )
    ivan_ref = core.store.get_hypernode(named.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert ivan_ref.kind is RefKind.M
    assert context.pronoun_refs["он"] == ivan_ref
    assert "он" not in context.existential_pronoun_anchors

    plan = service.prepare_external_plan(
        PerceptionResult(
            "Он улыбнулся.",
            assertions=(_unary("A3", "улыбнулся", "улыбнуться", "Он"),),
        ),
        context,
    )
    assert plan.candidate_ir.existential_bindings == ()
    assert plan.candidate_ir.discourse_refs == ()
    resolved = service.integrate_plan(plan, context)
    subject = core.store.get_hypernode(resolved.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert subject == ivan_ref


def test_cross_turn_existential_anchor_survives_context_persistence_roundtrip(tmp_path) -> None:
    core, context, service = _env()
    first = service.integrate_external(
        PerceptionResult(
            "Кто-то вошёл.",
            assertions=(
                _unary(
                    "A1", "вошёл", "войти", "Кто-то",
                    entity_ref="E1", quantified=True,
                ),
            ),
        ),
        context,
    )
    path = tmp_path / "ah.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False),
    )
    persistence.save(core, context=context)
    loaded = persistence.load()
    loaded_context = loaded.interaction_context
    assert loaded_context is not None
    anchor = loaded_context.existential_pronoun_anchors["он"]
    assert anchor.existential_ref.uid == first.existentials[0].ref.uid
    assert tuple(ref.uid for ref in anchor.member_refs) == tuple(
        ref.uid for ref in first.existentials[0].member_refs
    )

    loaded_service = IntegrationService(
        loaded.core,
        IntegrationConfig(0.4, 0.3, 0.2),
        discourse_morphology=_Morphology(),
    )
    second = loaded_service.integrate_external(
        PerceptionResult("Он сел.", assertions=(_unary("A2", "сел", "сесть", "Он"),)),
        loaded_context,
    )
    assert len(second.existentials) == 1
    assert len(second.existentials[0].member_refs) == 2
    assert loaded.core.store.find_entities_by_name("он", Domain.C) == ()


def test_cross_turn_anchor_and_new_unknown_get_distinct_bound_variables() -> None:
    core, context, service = _env()
    service.integrate_external(
        PerceptionResult(
            "Кто-то вошёл.",
            assertions=(
                _unary(
                    "A1", "вошёл", "войти", "Кто-то",
                    entity_ref="E1", quantified=True,
                ),
            ),
        ),
        context,
    )

    second = service.integrate_external(
        PerceptionResult(
            "Он увидел что-то.",
            assertions=(
                _binary(
                    "A2",
                    "увидел",
                    "увидеть",
                    ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он"),
                    ActantCandidate(
                        ActantRole.OBJECT,
                        mention="что-то",
                        entity_ref="E2",
                        quantifier=QuantifierCandidate(
                            QuantifierKind.EXISTS, "что-то"
                        ),
                    ),
                ),
            ),
        ),
        context,
    )
    existential = second.existentials[0]
    assert existential.variable_ids == (0, 1)
    node = core.store.get_hypernode(second.assertions[0].ref.uid)
    subject = node.actants[ActantRole.SUBJECT]
    obj = node.actants[ActantRole.OBJECT]
    assert isinstance(subject, BoundVar) and subject.local_id == 0
    assert isinstance(obj, BoundVar) and obj.local_id == 1
    root = core.store.get_element_any_domain(existential.ref.uid)
    assert isinstance(root, FunctionSymbol) and root.function_id == "EXISTS"
