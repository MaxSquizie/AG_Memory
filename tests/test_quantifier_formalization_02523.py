from __future__ import annotations

from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.diagnostics.acceptance_runner import _jsonable, canonical_ah_snapshot
from ah.diagnostics.semantic_oracle import SemanticOracleCase, evaluate_semantic_case
from ah.integration import IntegrationConfig, IntegrationService
from ah.llm import LLMResponse
from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Property, Ref
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QuantifierCandidate,
    QuantifierFormalizationError,
    QuantifierFormalizer,
    QuantifierKind,
    QuantifierProbeDecision,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import MorphInfo


ROOT = Path(__file__).resolve().parents[1]


class Grammar:
    name = "test"

    _NOUNS = {
        "студент": ("студент", "nomn", "masc"),
        "студента": ("студент", "gent", "masc"),
        "посылки": ("посылка", "gent", "femn"),
        "адресату": ("адресат", "datv", "masc"),
        "помещении": ("помещение", "loct", "neut"),
        "момент": ("момент", "accs", "masc"),
        "инструментом": ("инструмент", "ablt", "masc"),
        "инженер": ("инженер", "nomn", "masc"),
        "получателю": ("получатель", "datv", "masc"),
        "иван": ("иван", "nomn", "masc"),
    }
    _DETERMINERS = {
        "каждый",
        "каждом",
        "любой",
        "всякому",
        "единому",
    }
    _NUMERALS = {"один", "одной", "одним"}
    _PRONOUNS = {"кто-нибудь", "никто"}

    def analyze_all(self, word: str):
        token = word.casefold().replace("ё", "е")
        if token in self._NOUNS:
            lemma, case, gender = self._NOUNS[token]
            grammemes = {"Name"} if token == "иван" else set()
            return (
                MorphInfo(
                    lemma,
                    "NOUN",
                    case=case,
                    number="sing",
                    gender=gender,
                    grammemes=frozenset(grammemes),
                    score=1.0,
                ),
            )
        if token in self._DETERMINERS:
            return (
                MorphInfo(
                    token,
                    "ADJF",
                    grammemes=frozenset({"Apro"}),
                    score=1.0,
                ),
            )
        if token in self._NUMERALS:
            return (
                MorphInfo(
                    "один",
                    "ADJF",
                    grammemes=frozenset({"Apro", "Anum"}),
                    score=1.0,
                ),
            )
        if token in self._PRONOUNS:
            return (MorphInfo(token, "NPRO", score=1.0),)
        return ()

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def assertion(
    phrase: str,
    role: ActantRole = ActantRole.SUBJECT,
    *,
    negated: bool = False,
    quantifier: QuantifierCandidate | None = None,
) -> PerceptionResult:
    return PerceptionResult(
        f"{phrase} participates",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "participates",
                    "participate",
                    template_candidate=TemplateCandidate((role,)),
                ),
                (
                    ActantCandidate(
                        role,
                        mention=phrase,
                        normalized_hint=phrase.casefold(),
                        quantifier=quantifier,
                    ),
                ),
                negated=negated,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("phrase", "role", "decision", "kind", "restriction"),
    (
        ("хотя бы один студент", ActantRole.SUBJECT, "EXISTS", "EXISTS", "студент"),
        ("не менее одной посылки", ActantRole.OBJECT, "EXISTS", "EXISTS", "посылка"),
        ("ни единому адресату", ActantRole.RECIPIENT, "NOT_EXISTS", "NOT_EXISTS", "адресат"),
        ("в каждом помещении", ActantRole.LOCATION, "FORALL", "FORALL", "помещение"),
        ("в любой момент", ActantRole.TIME, "FORALL", "FORALL", "момент"),
        ("ни одним инструментом", ActantRole.TOOL, "NOT_EXISTS", "NOT_EXISTS", "инструмент"),
        ("далеко не каждый инженер", ActantRole.SUBJECT, "NOT_FORALL", "NOT_FORALL", "инженер"),
        ("всякому получателю", ActantRole.RECIPIENT, "FORALL", "FORALL", "получатель"),
    ),
)
def test_semantic_probe_classifies_paraphrases_without_surface_rules(
    phrase: str,
    role: ActantRole,
    decision: str,
    kind: str,
    restriction: str,
) -> None:
    calls: list[str] = []

    def resolve(source, predicate, actant, negated):
        calls.append(actant.mention or "")
        return QuantifierProbeDecision(decision)

    result = QuantifierFormalizer(Grammar()).formalize(
        assertion(phrase, role), resolver=resolve
    )
    actant = result.assertions[0].actants[0]
    assert calls == [phrase]
    assert actant.entity_ref == f"Q:A1:{role.value}:0"
    assert actant.quantifier is not None
    assert actant.quantifier.kind.value == kind
    assert actant.quantifier.restriction_lemma == restriction
    assert actant.normalized_hint == restriction


@pytest.mark.parametrize("phrase", ("Иван", "AG-42", "Кванториум", "студент"))
def test_names_terms_abbreviations_and_plain_nouns_do_not_become_quantifiers(
    phrase: str,
) -> None:
    calls = 0

    def resolve(*_args):
        nonlocal calls
        calls += 1
        return QuantifierProbeDecision.EXISTS

    result = QuantifierFormalizer(Grammar()).formalize(
        assertion(phrase), resolver=resolve
    )
    assert calls == 0
    assert result.assertions[0].actants[0].quantifier is None


def test_ambiguous_semantic_decision_fails_closed() -> None:
    with pytest.raises(QuantifierFormalizationError, match="ambiguous"):
        QuantifierFormalizer(Grammar()).formalize(
            assertion("хотя бы один студент"),
            resolver=lambda *_args: QuantifierProbeDecision.AMBIGUOUS,
        )


def test_universal_without_source_grounded_class_fails_closed() -> None:
    with pytest.raises(QuantifierFormalizationError, match="restriction"):
        QuantifierFormalizer(Grammar()).formalize(
            assertion("каждый"),
            resolver=lambda *_args: QuantifierProbeDecision.FORALL,
        )


def test_explicit_negative_binder_cannot_silently_consume_body_negation() -> None:
    candidate = QuantifierCandidate(
        QuantifierKind.NOT_FORALL,
        "далеко не каждый инженер",
        "инженер",
    )
    with pytest.raises(QuantifierFormalizationError, match="scope metadata"):
        QuantifierFormalizer(Grammar()).formalize(
            assertion(candidate.surface, negated=True, quantifier=candidate)
        )


def test_quantifier_probe_uses_one_non_thinking_fixed_label_call() -> None:
    class Backend:
        def __init__(self) -> None:
            self.calls = []

        def generate(self, prompt, *, system="", override=None, role="generic"):
            self.calls.append((role, prompt, system, dict(override or {})))
            return LLMResponse("NOT_FORALL", {})

    backend = Backend()
    parser = AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            morphology_backend="none",
            prompt_dir=ROOT / "prompts" / "perception",
            generation=LLMRoleSettings(max_new_tokens=8),
            retry_attempts=0,
        ),
        morphology=Grammar(),
    )
    decision = parser._resolve_quantifier_candidate(
        "Not every engineer arrived",
        PredicateCandidate("arrived", "arrive"),
        ActantCandidate(ActantRole.SUBJECT, mention="not every engineer"),
        True,
    )
    assert decision is QuantifierProbeDecision.NOT_FORALL
    assert len(backend.calls) == 1
    role, prompt, _system, override = backend.calls[0]
    assert role == "semantic_quantifier"
    assert override["enable_thinking"] is False
    assert "TARGET ROLE:\nSUBJECT" in prompt
    assert "CHOICES:\nNONE\nEXISTS\nNOT_EXISTS\nFORALL\nNOT_FORALL\nAMBIGUOUS" in prompt
    assert "UID" not in prompt.upper()


def _environment():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Agent", "str")}, uid="M_SELF"
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "User", "str")}, uid="M_USER"
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid),
        user_ref=core.ref(user_entity.uid),
    )
    service = IntegrationService(
        core,
        IntegrationConfig(0.4, 0.3, 0.2),
        discourse_morphology=Grammar(),
    )
    return core, context, service


def _function(core: AHCore, ref: Ref) -> FunctionSymbol:
    item = core.store.get_element_any_domain(ref.uid)
    assert isinstance(item, FunctionSymbol)
    return item


def test_restricted_existential_has_exact_class_and_body_formula() -> None:
    core, context, service = _environment()
    phrase = "хотя бы один студент"
    commit = service.integrate_external(
        assertion(
            phrase,
            quantifier=QuantifierCandidate(
                QuantifierKind.EXISTS,
                phrase,
                "студент",
            ),
        ),
        context,
    )
    assert len(commit.existentials) == 1
    quantified = commit.existentials[0]
    exists = _function(core, quantified.ref)
    variable, restricted_ref = exists.operands
    assert isinstance(variable, BoundVar)
    assert isinstance(restricted_ref, Ref)
    restricted = _function(core, restricted_ref)
    assert restricted.function_id == "AND"
    class_ref, body_ref = restricted.operands
    assert body_ref == quantified.member_refs[0]
    class_node = core.store.get_hypernode(class_ref.uid)
    assert class_node.actants == {ActantRole.SUBJECT: variable}
    class_template = core.store.get_template(class_node.template.uid)
    class_symbol = core.store.get_symbol(class_template.predicate.uid)
    assert "студент" in class_symbol.forms
    assert core.store.find_entities_by_name(phrase.casefold(), Domain.C) == ()


def test_restricted_existential_context_anchor_preserves_restriction() -> None:
    _core, context, service = _environment()
    phrase = "хотя бы один студент"
    service.integrate_external(
        assertion(
            phrase,
            quantifier=QuantifierCandidate(
                QuantifierKind.EXISTS,
                phrase,
                "студент",
            ),
        ),
        context,
    )
    anchor = context.existential_pronoun_anchors["он"]
    assert anchor.restriction_lemma == "студент"


def test_semantic_oracle_checks_typed_candidate_and_complete_binder_spine() -> None:
    core, context, service = _environment()
    phrase = "хотя бы один студент"
    source = assertion(
        phrase,
        quantifier=QuantifierCandidate(
            QuantifierKind.EXISTS,
            phrase,
            "студент",
        ),
    )
    plan = service.prepare_external_plan(source, context)
    commit = service.integrate_plan(plan, context)
    record = {
        "status": "OK",
        "perception_result": _jsonable(plan.perception),
        "integration_commit": _jsonable(commit),
    }
    oracle = SemanticOracleCase(
        1,
        source.source_text,
        "EXACT",
        {
            "perception": {
                "must_parse": True,
                "assertions": [
                    {
                        "key": "a1",
                        "predicate": "participate",
                        "status": "ASSERTED",
                        "negated": False,
                        "roles": {
                            "SUBJECT": {
                                "quantifier": {
                                    "kind": "EXISTS",
                                    "restriction": "студент",
                                }
                            }
                        },
                    }
                ],
                "queries": [],
                "relations": [],
                "conditionals": [],
            },
            "integration": {
                "must_succeed": True,
                "domains": {"a1": "C"},
                "quantifiers": [
                    {
                        "kind": "EXISTS",
                        "variables": 1,
                        "restriction": "студент",
                        "members": ["a1"],
                    }
                ],
            },
        },
    )
    verdict = evaluate_semantic_case(
        record,
        oracle,
        canonical_ah_snapshot(type("Services", (), {"core": core})()),
        {},
    )
    assert verdict.status == "PASS", verdict.failures
