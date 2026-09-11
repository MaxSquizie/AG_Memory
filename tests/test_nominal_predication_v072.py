from __future__ import annotations

from pathlib import Path

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import MorphInfo
from legacy_semantic_fixture import legacy_semantic_answer

PROJECT = Path(__file__).resolve().parents[1]


class NominalMorphology:
    name = "fake-nominal-v072"

    _MAP = {
        "крипл": (MorphInfo("криплый", "ADJS", case=None, number="sing", score=1.0),),
        "это": (MorphInfo("это", "NPRO", case="nomn", number="sing", score=1.0),),
        "название": (MorphInfo("название", "NOUN", case="nomn", number="sing", score=1.0),),
        "моего": (MorphInfo("мой", "ADJF", case="gent", number="sing", score=1.0),),
        "проекта": (MorphInfo("проект", "NOUN", case="gent", number="sing", score=1.0),),
        "проект": (MorphInfo("проект", "NOUN", case="nomn", number="sing", score=1.0),),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
        "одновременно": (MorphInfo("одновременно", "ADVB", score=1.0),),
        "с": (MorphInfo("с", "PREP", score=1.0),),
        "этим": (MorphInfo("это", "NPRO", case="ablt", number="sing", score=1.0),),
        "имя": (MorphInfo("имя", "NOUN", case="nomn", number="sing", score=1.0),),
        "ии": (MorphInfo("ии", "NOUN", case="gent", number="sing", score=1.0),),
        "докажи": (MorphInfo("доказать", "VERB", mood="impr", number="sing", score=1.0),),
        "что": (MorphInfo("что", "CONJ", score=1.0),),
        "москва": (MorphInfo("москва", "NOUN", case="nomn", number="sing", score=1.0),),
        "город": (MorphInfo("город", "NOUN", case="nomn", number="sing", score=1.0),),
        "яблоко": (MorphInfo("яблоко", "NOUN", case="nomn", number="sing", score=1.0),),
        "красное": (MorphInfo("красный", "ADJF", case="nomn", number="sing", score=1.0),),
        "столица": (MorphInfo("столица", "NOUN", case="nomn", number="sing", score=1.0),),
        "россии": (MorphInfo("россия", "NOUN", case="gent", number="sing", score=1.0),),
        "миша": (MorphInfo("миша", "NOUN", case="nomn", number="sing", score=1.0),),
        "человек": (MorphInfo("человек", "NOUN", case="nomn", number="sing", score=1.0),),
    }

    def analyze_all(self, word: str):
        return self._MAP.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class Backend:
    def __init__(self) -> None:
        self.roles: list[str] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.roles.append(role)
        if role == "perception_referential_predicative":
            return LLMResponse("REFERENTIAL", {})
        if role == "semantic_nominal_label_semantics":
            if "NOMINAL PREDICATE:\nназвание" in prompt or "NOMINAL PREDICATE:\nимя" in prompt:
                return LLMResponse("YES", {})
            return LLMResponse("NO", {})
        if role == "perception_nominal_projection_target":
            return LLMResponse("C1", {})
        if role == "perception_role_cue":
            # The only semantic complements in the target regression are the
            # owner/content NPs of nominal predicates.
            if "TARGET:\nмоего проекта" in prompt or "TARGET:\nмоего ИИ" in prompt:
                return LLMResponse("AFFECTED_OR_CONTENT", {})
            if "TARGET:\nКрипл" in prompt:
                return LLMResponse("ACTOR_OR_EXPERIENCER", {})
            if "TARGET:\nРоссии" in prompt:
                return LLMResponse("AFFECTED_OR_CONTENT", {})
        if role == "perception_frame_relation":
            return LLMResponse("CONTENT_LINK", {})
        if role == "perception_coordination_shared_actant":
            return LLMResponse("SHARED", {})
        if role == "perception_act_type":
            # Used only if deterministic force cannot settle a synthetic fixture.
            if "?" in prompt:
                return LLMResponse("QUERY", {})
            if "Докажи" in prompt:
                return LLMResponse("COMMAND", {})
            return LLMResponse("ASSERTION", {})
        fallback = legacy_semantic_answer(role, prompt)
        if fallback is not None:
            return LLMResponse(str(fallback), {})
        raise AssertionError(f"unexpected probe {role}:\n{prompt}")


def parser(backend: Backend | None = None) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend or Backend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=NominalMorphology(),
    )


def roles(assertion):
    return {item.role: item for item in assertion.actants}


def test_live_v073_projection_failure_is_removed_from_protocol():
    backend = Backend()
    parsed = parser(backend).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    stages = [trace.stage for trace in parsed.traces]
    # Old weak fixed-choice formulations failed on the live Qwen even after
    # syntax was correct. v0.12.76 asks one isolated semantic paraphrase in the
    # deep-semantic role. Both complements contain one noun, so no target-selection
    # probe is needed.
    assert stages.count("nominal_label_semantics") == 2
    assert "nominal_subject_projection" not in stages
    assert "nominal_projection_relation" not in stages
    assert "nominal_projection_target" not in stages
    assert {item.predicate.lookup_form.casefold() for item in parsed.perception.assertions} == {
        "название", "имя", "проект", "ии"
    }


def test_exact_kripl_compound_nominal_predication_splits_into_two_frames():
    backend = Backend()
    result = parser(backend).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    assertions = result.perception.assertions
    assert len(assertions) == 4
    by_predicate = {item.predicate.lookup_form.casefold(): item for item in assertions}
    assert {item.predicate.lookup_form.casefold() for item in assertions} == {
        "название", "имя", "проект", "ии"
    }
    assert all(item.predicate.lookup_form != "криплый" for item in assertions)

    first = by_predicate["название"]
    second = by_predicate["имя"]
    r1, r2 = roles(first), roles(second)
    assert r1[ActantRole.SUBJECT].mention == "Крипл"
    assert r2[ActantRole.SUBJECT].mention == "Крипл"
    assert r1[ActantRole.OBJECT].mention == "моего проекта"
    assert r2[ActantRole.OBJECT].mention == "моего ИИ"
    assert ActantRole.TIME not in r1 and ActantRole.TIME not in r2
    assert ActantRole.MATERIAL not in r1 and ActantRole.MATERIAL not in r2
    assert ActantRole.RECIPIENT not in r1 and ActantRole.RECIPIENT not in r2
    assert "perception_referential_predicative" not in backend.roles




class PredicativeVotingBackend(Backend):
    """Reproduce the live Qwen answer without letting it override syntax."""

    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "perception_referential_predicative":
            self.roles.append(role)
            return LLMResponse("PREDICATIVE", {})
        return super().generate(prompt, system=system, override=override, role=role)


def test_explicit_copular_shell_does_not_let_semantic_probe_override_direction():
    backend = PredicativeVotingBackend()
    result = parser(backend).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    assertions = result.perception.assertions
    by_predicate = {item.predicate.lookup_form.casefold(): item for item in assertions}
    assert set(by_predicate) == {"название", "имя", "проект", "ии"}
    assert "perception_referential_predicative" not in backend.roles

    for key in ("название", "имя", "проект", "ии"):
        subject = roles(by_predicate[key])[ActantRole.SUBJECT]
        assert subject.mention == "Крипл"
        assert subject.evidence is not None
        assert (subject.evidence.start, subject.evidence.end) == (0, 5)

    explicit_mentions = {
        actant.mention
        for key in ("название", "имя")
        for actant in by_predicate[key].actants
    }
    assert "этим" not in explicit_mentions
    assert "одновременно" not in explicit_mentions


def test_direct_nominal_query_uses_right_nominal_as_predicate():
    result = parser().parse("Крипл это проект?")
    assert not result.perception.assertions
    assert len(result.perception.queries) == 1
    query = result.perception.queries[0]
    assert query.predicate.lookup_form == "проект"
    assert {a.role: a.mention for a in query.actants} == {ActantRole.SUBJECT: "Крипл"}


def test_dash_nominal_query_uses_same_semantic_frame():
    result = parser().parse("Крипл - проект?")
    query = result.perception.queries[0]
    assert query.predicate.lookup_form == "проект"
    assert {a.role: a.mention for a in query.actants} == {ActantRole.SUBJECT: "Крипл"}


def test_embedded_proof_command_keeps_nominal_proposition_as_child_frame():
    result = parser().parse("Докажи что Крипл - проект")
    assert len(result.perception.commands) == 1
    assert result.perception.commands[0].predicate.lookup_form == "доказать"
    embedded = [item for item in result.perception.assertions if item.predicate.lookup_form == "проект"]
    assert len(embedded) == 1
    assert roles(embedded[0])[ActantRole.SUBJECT].mention == "Крипл"
    assert result.perception.act_dependencies


def test_generic_common_noun_nominal_predication_needs_no_name_marker():
    backend = Backend()
    result = parser(backend).parse("Москва — город")
    assertion = result.perception.assertions[0]
    assert assertion.predicate.lookup_form == "город"
    assert roles(assertion)[ActantRole.SUBJECT].mention == "Москва"
    # Morphology already establishes a nominal left term; no semantic rescue probe.
    assert "perception_referential_predicative" not in backend.roles


def test_adjectival_zero_copula_keeps_existing_implicit_be_behavior():
    result = parser().parse("Яблоко красное")
    assertion = result.perception.assertions[0]
    assert assertion.predicate.lookup_form in {"быть", "бывать"}
    assert {a.role: a.mention for a in assertion.actants} == {
        ActantRole.SUBJECT: "Яблоко",
        ActantRole.STATE: "красное",
    }


def test_two_independent_nominal_sentences_each_get_their_own_frame():
    result = parser().parse("Москва — город. Крипл — проект")
    assertions = result.perception.assertions
    assert [item.predicate.lookup_form for item in assertions] == ["город", "проект"]
    assert [roles(item)[ActantRole.SUBJECT].mention for item in assertions] == ["Москва", "Крипл"]


def test_exact_compound_integrates_as_two_n_with_one_shared_kripl_entity():
    from ah.agent import InteractionContext
    from ah.core import AHCore, SequentialUidGenerator
    from ah.integration import IntegrationConfig, IntegrationService, TemplateCompletionService
    from ah.model import Domain, Hypernode, Property
    from ah.perception import TemplateCandidate

    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, properties={"name": Property("name", "Agent", "str")},
        meta={"identity_role": "SELF"},
    )
    user_entity = core.add_entity(
        Domain.P, properties={"name": Property("name", "User", "str")},
        meta={"identity_role": "USER"},
    )
    context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
    integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))

    parsed = parser().parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    ).perception

    class ExplicitTemplateCompletion:
        @staticmethod
        def propose_template_candidate(source_text, predicate, filled_roles, role_bindings=()):
            del source_text, predicate, role_bindings
            return TemplateCandidate(tuple(filled_roles))

    completed = TemplateCompletionService(integration, ExplicitTemplateCompletion()).complete(parsed)
    commit = integration.integrate_external(completed, context)

    assert len(commit.assertions) == 4
    nodes = [core.store.get_hypernode(item.ref.uid) for item in commit.assertions]
    assert all(isinstance(node, Hypernode) for node in nodes)
    templates = [core.store.get_template(node.template.uid) for node in nodes]
    predicate_forms = [core.store.get_symbol(template.predicate.uid).forms for template in templates]
    assert any("название" in forms for forms in predicate_forms)
    assert any("имя" in forms for forms in predicate_forms)
    assert any("проект" in forms for forms in predicate_forms)
    assert any("ии" in {form.casefold() for form in forms} for forms in predicate_forms)

    subjects = [node.actants[ActantRole.SUBJECT] for node in nodes]
    assert len({ref.uid for ref in subjects}) == 1
    kripl = core.store.get_element_any_domain(subjects[0].uid)
    assert kripl.properties["name"].value == "Крипл"


class LiveV074FailureBackend(Backend):
    """Reproduce the observed v0.12.74 disagreement on the old relation probe.

    The old whole-relation wording returned LABELS_COMPLEMENT for `название` but
    OTHER_RELATION for `имя`.  v0.12.75 must not call that probe at all.  The new
    bounded task classifies only the local predicate sense, for which both are
    unambiguously label/identifier predicates.
    """

    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "perception_nominal_projection_relation":
            self.roles.append(role)
            if "NOMINAL PREDICATE:\nназвание" in prompt:
                return LLMResponse("LABELS_COMPLEMENT", {})
            if "NOMINAL PREDICATE:\nимя" in prompt:
                return LLMResponse("OTHER_RELATION", {})
        return super().generate(prompt, system=system, override=override, role=role)


def test_live_v074_relation_disagreement_cannot_drop_ai_projection():
    backend = LiveV074FailureBackend()
    parsed = parser(backend).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    predicates = {item.predicate.lookup_form.casefold() for item in parsed.perception.assertions}
    assert predicates == {"название", "имя", "проект", "ии"}
    assert "perception_nominal_projection_relation" not in backend.roles
    assert backend.roles.count("semantic_nominal_label_semantics") == 2


class LiveV075FailureBackend(Backend):
    """Reproduce the observed weak-probe failure from the real v0.12.75 run."""

    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "perception_nominal_predicate_family":
            self.roles.append(role)
            return LLMResponse("OTHER_NOMINAL", {})
        return super().generate(prompt, system=system, override=override, role=role)


def test_live_v075_weak_family_failure_is_not_on_runtime_path():
    backend = LiveV075FailureBackend()
    parsed = parser(backend).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    predicates = {item.predicate.lookup_form.casefold() for item in parsed.perception.assertions}
    assert predicates == {"название", "имя", "проект", "ии"}
    assert "perception_nominal_predicate_family" not in backend.roles
    assert backend.roles.count("semantic_nominal_label_semantics") == 2


class DeepSemanticOverrideBackend(Backend):
    def __init__(self) -> None:
        super().__init__()
        self.semantic_overrides = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "semantic_nominal_label_semantics":
            self.semantic_overrides.append(dict(override or {}))
        return super().generate(prompt, system=system, override=override, role=role)


def test_nominal_label_semantics_uses_isolated_non_thinking_request_mode():
    backend = DeepSemanticOverrideBackend()
    parser(backend).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    assert len(backend.semantic_overrides) == 2
    assert all(item.get("enable_thinking") is False for item in backend.semantic_overrides)
    assert all(item.get("temperature") == 0.0 for item in backend.semantic_overrides)
    assert all(item.get("max_new_tokens") <= 8 for item in backend.semantic_overrides)




class ThinkingProtocolBreakBackend(Backend):
    """Model fixture that reproduces the live thinking/protocol failure."""

    def __init__(self) -> None:
        super().__init__()
        self.semantic_overrides: list[dict] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "semantic_nominal_label_semantics":
            ov = dict(override or {})
            self.roles.append(role)
            self.semantic_overrides.append(ov)
            if ov.get("enable_thinking"):
                # The live thinking checkpoint can spend the response on reasoning
                # and violate the exact protocol instead of returning YES/NO.
                return LLMResponse("I need to reason about the relation first...", {})
            if "NOMINAL PREDICATE:\nназвание" in prompt or "NOMINAL PREDICATE:\nимя" in prompt:
                return LLMResponse("YES", {})
            return LLMResponse("NO", {})
        return super().generate(prompt, system=system, override=override, role=role)


def test_live_thinking_protocol_failure_is_prevented_by_forcing_non_thinking():
    backend = ThinkingProtocolBreakBackend()
    result = parser(backend).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    predicates = {item.predicate.lookup_form.casefold() for item in result.perception.assertions}
    assert predicates == {"название", "имя", "проект", "ии"}
    assert len(backend.semantic_overrides) == 2
    assert all(item.get("enable_thinking") is False for item in backend.semantic_overrides)


class InvalidOptionalProjectionBackend(Backend):
    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "semantic_nominal_label_semantics":
            self.roles.append(role)
            return LLMResponse("<think>unfinished reasoning only</think>", {})
        return super().generate(prompt, system=system, override=override, role=role)


def test_invalid_optional_nominal_projection_does_not_discard_primary_parse():
    result = parser(InvalidOptionalProjectionBackend()).parse(
        "Крипл - это название моего проекта и одновременно с этим это имя моего ИИ"
    )
    predicates = {item.predicate.lookup_form.casefold() for item in result.perception.assertions}
    # Projection fails closed, but the two explicit source facts survive.
    assert predicates == {"название", "имя"}
    failures = [t for t in result.traces if t.stage == "nominal_label_semantics" and t.error]
    assert len(failures) == 2
    assert all("expected exactly one of: YES, NO, UNCLEAR" in t.error for t in failures)


def test_nominal_label_semantics_is_not_related_noun_copy():
    backend = Backend()
    result = parser(backend).parse("Москва — столица России")
    predicates = [item.predicate.lookup_form.casefold() for item in result.perception.assertions]
    assert predicates == ["столица"]
    assert "россия" not in predicates
    assert "semantic_nominal_label_semantics" in backend.roles


def test_kripl_compound_fact_supports_project_and_ai_exists_but_not_unrelated_class():
    from ah.agent import InteractionContext
    from ah.config import InferenceSettings
    from ah.core import AHCore, SequentialUidGenerator
    from ah.inference import InferenceEngine, LogicalStatus, QueryGoalBuilder
    from ah.integration import IntegrationConfig, IntegrationService, TemplateCompletionService
    from ah.model import Domain, Property
    from ah.perception import TemplateCandidate

    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, properties={"name": Property("name", "Agent", "str")},
        meta={"identity_role": "SELF"},
    )
    user_entity = core.add_entity(
        Domain.P, properties={"name": Property("name", "User", "str")},
        meta={"identity_role": "USER"},
    )
    context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
    integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))

    class ExplicitTemplateCompletion:
        @staticmethod
        def propose_template_candidate(source_text, predicate, filled_roles, role_bindings=()):
            del source_text, predicate, role_bindings
            return TemplateCandidate(tuple(filled_roles))

    completion = TemplateCompletionService(integration, ExplicitTemplateCompletion())

    def integrate_text(source: str):
        parsed = parser().parse(source).perception
        completed = completion.complete(parsed)
        return integration.integrate_external(completed, context)

    integrate_text("Крипл - это название моего проекта и одновременно с этим это имя моего ИИ")
    # Establish the unrelated predicate vocabulary without asserting it about Kripl.
    integrate_text("Миша — человек")

    builder = QueryGoalBuilder(core)
    engine = InferenceEngine(core, InferenceSettings(max_depth=6))

    statuses = {}
    for text, key in (
        ("Крипл - проект?", "project"),
        ("Крипл - ИИ?", "ai"),
        ("Крипл - человек?", "human"),
    ):
        query = parser().parse(text).perception.queries[0]
        built = builder.build(query, context)
        assert built.goal is not None, built.diagnostics
        statuses[key] = engine.solve(built.goal).status

    assert statuses["project"] is LogicalStatus.PROVED
    assert statuses["ai"] is LogicalStatus.PROVED
    assert statuses["human"] is LogicalStatus.UNKNOWN
