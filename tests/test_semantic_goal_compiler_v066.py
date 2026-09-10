from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
from ah.config import InferenceSettings, IntegrationSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    AllOfGoal,
    CauseEntailmentGoal,
    InferenceEngine,
    LogicalStatus,
    RelationGoal,
    SemanticGoalCompiler,
)
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActRelationCandidate,
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    CommandCandidate,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    QueryCandidate,
    QueryMode,
    SituationRelationCandidate,
    TemplateCandidate,
    apply_speech_act_scoping,
)


def _runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P,
        properties={"name": Property("name", "Agent", "str")},
        meta={"identity_role": "SELF"},
    )
    user_entity = core.add_entity(
        Domain.P,
        properties={"name": Property("name", "User", "str")},
        meta={"identity_role": "USER"},
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid)
    )
    integration = IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings()))
    engine = InferenceEngine(core, InferenceSettings(max_depth=6, max_expanded_states=500))
    return core, context, integration, engine


def _classification_assertion(local_id: str, subject: str, state: str, *, status=AssertionStatus.ASSERTED):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            "is",
            "be",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention=subject),
            ActantCandidate(ActantRole.STATE, mention=state),
        ),
        status=status,
    )


def _event_assertion(local_id: str, who: str, state: str, *, status=AssertionStatus.ASSERTED):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            "state",
            "state",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention=who),
            ActantCandidate(ActantRole.STATE, mention=state),
        ),
        status=status,
    )


def _command(local_id: str = "C1", *, proposition=None):
    actants = ()
    roles = ()
    if proposition is not None:
        actants = (ActantCandidate(ActantRole.OBJECT, proposition=proposition),)
        roles = (ActantRole.OBJECT,)
    return CommandCandidate(
        PredicateCandidate("request", "request", template_candidate=TemplateCandidate(roles)),
        actants=actants,
        local_id=local_id,
    )


def test_asserted_typed_is_a_materializes_structural_link():
    core, context, integration, _engine = _runtime()
    result = PerceptionResult(
        source_text="Kripl is AI",
        assertions=(_classification_assertion("A1", "Kripl", "AI"),),
        act_relations=(
            ActRelationCandidate("IS-A", "A1", ActantRole.SUBJECT, ActantRole.STATE),
        ),
    )
    commit = integration.integrate_external(result, context)
    relation = next(item for item in commit.relations if item.relation_id == "IS-A")
    assert core.store.find_link("IS-A", relation.source.uid, relation.target.uid) is not None


def test_embedded_is_a_uses_relation_chain_and_never_self_materializes():
    core, context, integration, engine = _runtime()
    kripl = core.add_entity(Domain.C, properties={"name": Property("name", "Kripl", "str")})
    digital = core.add_entity(Domain.C, properties={"name": Property("name", "Digital agent", "str")})
    ai = core.add_entity(Domain.C, properties={"name": Property("name", "AI", "str")})
    core.add_link("IS-A", core.ref(kripl.uid), core.ref(digital.uid), 0.2)
    core.add_link("IS-A", core.ref(digital.uid), core.ref(ai.uid), 0.2)

    raw = PerceptionResult(
        source_text="request [Kripl is AI]",
        assertions=(_classification_assertion("A1", "Kripl", "AI"),),
        commands=(_command(),),
        act_dependencies=(ActDependencyCandidate("C1", "A1", ActDependencyKind.SUBORDINATE),),
        act_relations=(ActRelationCandidate("IS-A", "A1", ActantRole.SUBJECT, ActantRole.STATE),),
    )
    perception = apply_speech_act_scoping(raw)
    commit = integration.integrate_external(perception, context)

    assert core.store.find_link("IS-A", kripl.uid, ai.uid) is None
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1
    assert isinstance(built[0].goal.goal.target, RelationGoal)
    outcome = engine.solve(built[0].goal)
    assert outcome.status is LogicalStatus.PROVED
    trace_uids = [ref.uid for ref in outcome.uid_trace]
    assert trace_uids[0] == kripl.uid
    assert trace_uids[-1] == ai.uid
    assert digital.uid in trace_uids


def test_direct_query_compiles_typed_is_a_without_predicate_marker_dispatch():
    core, context, integration, engine = _runtime()
    kripl = core.add_entity(Domain.C, properties={"name": Property("name", "Kripl", "str")})
    digital = core.add_entity(Domain.C, properties={"name": Property("name", "Digital agent", "str")})
    ai = core.add_entity(Domain.C, properties={"name": Property("name", "AI", "str")})
    core.add_link("IS-A", core.ref(kripl.uid), core.ref(digital.uid), 0.2)
    core.add_link("IS-A", core.ref(digital.uid), core.ref(ai.uid), 0.2)

    query = QueryCandidate(
        PredicateCandidate("whatever", "whatever", template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE))),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Kripl"),
            ActantCandidate(ActantRole.STATE, mention="AI"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    perception = PerceptionResult(
        source_text="semantic query",
        queries=(query,),
        act_relations=(ActRelationCandidate("IS-A", "Q1", ActantRole.SUBJECT, ActantRole.STATE),),
    )
    commit = integration.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1
    assert isinstance(built[0].goal.goal.target, RelationGoal)
    assert engine.solve(built[0].goal).status is LogicalStatus.PROVED


def _install_event_chain(core, context, integration, relation_id: str):
    prior = PerceptionResult(
        source_text="three situations",
        assertions=(
            _event_assertion("P1", "System", "one"),
            _event_assertion("P2", "System", "two"),
            _event_assertion("P3", "System", "three"),
        ),
    )
    commit = integration.integrate_external(prior, context)
    refs = [item.ref for item in commit.assertions]
    core.add_link(relation_id, refs[0], refs[1], 0.2)
    core.add_link(relation_id, refs[1], refs[2], 0.2)
    return refs


def test_embedded_follow_compiles_to_transitive_relation_goal_without_leaking_direct_link():
    core, context, integration, engine = _runtime()
    refs = _install_event_chain(core, context, integration, "FOLLOW")
    raw = PerceptionResult(
        source_text="request relation",
        assertions=(
            _event_assertion("A1", "System", "one"),
            _event_assertion("A3", "System", "three"),
        ),
        commands=(_command(),),
        act_dependencies=(
            ActDependencyCandidate("C1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("C1", "A3", ActDependencyKind.SUBORDINATE),
        ),
        relations=(SituationRelationCandidate("FOLLOW", "A1", "A3"),),
    )
    perception = apply_speech_act_scoping(raw)
    commit = integration.integrate_external(perception, context)
    assert core.store.find_link("FOLLOW", refs[0].uid, refs[2].uid) is None
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1
    goal = built[0].goal.goal.target
    assert isinstance(goal, RelationGoal) and goal.relation_id == "FOLLOW"
    outcome = engine.solve(built[0].goal)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.logical_depth == 2


def test_cause_entailment_uses_asserted_source_as_explicit_premise():
    core, context, integration, engine = _runtime()
    refs = _install_event_chain(core, context, integration, "CAUSE")
    raw = PerceptionResult(
        source_text="given source, request effect",
        assertions=(
            _event_assertion("A1", "System", "one"),
            _event_assertion("A3", "System", "three"),
        ),
        commands=(_command(),),
        act_dependencies=(ActDependencyCandidate("C1", "A3", ActDependencyKind.SUBORDINATE),),
        relations=(SituationRelationCandidate("CAUSE", "A1", "A3"),),
    )
    perception = apply_speech_act_scoping(raw)
    assert perception.assertions[0].status is AssertionStatus.ASSERTED
    assert perception.assertions[1].status is AssertionStatus.EMBEDDED
    commit = integration.integrate_external(perception, context)
    assert core.store.find_link("CAUSE", refs[0].uid, refs[2].uid) is None
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1
    assert isinstance(built[0].goal.goal.target, CauseEntailmentGoal)
    assert built[0].goal.premise_refs == (refs[0],)
    outcome = engine.solve(built[0].goal)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.logical_depth == 2


def test_explicit_proposition_and_compiles_to_all_of_but_or_is_not_faked_as_and():
    core, context, integration, engine = _runtime()
    a = core.add_entity(Domain.C, properties={"name": Property("name", "A", "str")})
    b = core.add_entity(Domain.C, properties={"name": Property("name", "B", "str")})
    c = core.add_entity(Domain.C, properties={"name": Property("name", "C", "str")})
    d = core.add_entity(Domain.C, properties={"name": Property("name", "D", "str")})
    core.add_link("IS-A", core.ref(a.uid), core.ref(b.uid), 0.2)
    core.add_link("IS-A", core.ref(c.uid), core.ref(d.uid), 0.2)

    assertions = (
        _classification_assertion("A1", "A", "B"),
        _classification_assertion("A2", "C", "D"),
    )
    relations = (
        ActRelationCandidate("IS-A", "A1", ActantRole.SUBJECT, ActantRole.STATE),
        ActRelationCandidate("IS-A", "A2", ActantRole.SUBJECT, ActantRole.STATE),
    )
    and_expr = PropositionExprCandidate(
        PropositionOperator.AND,
        members=(PropositionExprCandidate.ref_expr("A1"), PropositionExprCandidate.ref_expr("A2")),
    )
    raw = PerceptionResult(
        source_text="request both",
        assertions=assertions,
        commands=(_command(proposition=and_expr),),
        act_dependencies=(
            ActDependencyCandidate("C1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("C1", "A2", ActDependencyKind.SUBORDINATE),
        ),
        act_relations=relations,
    )
    perception = apply_speech_act_scoping(raw)
    commit = integration.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1
    assert isinstance(built[0].goal.goal.target, AllOfGoal)
    assert engine.solve(built[0].goal).status is LogicalStatus.PROVED

    or_expr = PropositionExprCandidate(
        PropositionOperator.OR,
        members=(PropositionExprCandidate.ref_expr("A1"), PropositionExprCandidate.ref_expr("A2")),
    )
    raw_or = PerceptionResult(
        source_text="request either",
        assertions=assertions,
        commands=(_command(proposition=or_expr),),
        act_dependencies=raw.act_dependencies,
        act_relations=relations,
    )
    perception_or = apply_speech_act_scoping(raw_or)
    commit_or = integration.integrate_external(perception_or, context)
    built_or = SemanticGoalCompiler(core).build(commit_or, context, perception_or)
    assert len(built_or) == 1
    assert built_or[0].goal is None
    assert built_or[0].diagnostics == ("semantic:OR_goal_not_supported",)

    xor_expr = PropositionExprCandidate(
        PropositionOperator.XOR,
        members=(
            PropositionExprCandidate.ref_expr("A1"),
            PropositionExprCandidate.ref_expr("A2"),
        ),
    )
    raw_xor = PerceptionResult(
        source_text="request exactly one",
        assertions=assertions,
        commands=(_command(proposition=xor_expr),),
        act_dependencies=raw.act_dependencies,
        act_relations=relations,
    )
    perception_xor = apply_speech_act_scoping(raw_xor)
    commit_xor = integration.integrate_external(perception_xor, context)
    built_xor = SemanticGoalCompiler(core).build(
        commit_xor, context, perception_xor
    )
    assert len(built_xor) == 1
    assert built_xor[0].goal is None
    assert built_xor[0].diagnostics == (
        "semantic:XOR_goal_not_supported",
    )


def test_goal_semantic_service_adds_typed_relation_from_bounded_classifier():
    from ah.perception import GoalSemanticService

    class Classifier:
        def __init__(self):
            self.calls = []
        def classify_act_relation(self, source_text, act_ref, predicate, actants):
            self.calls.append((source_text, act_ref, tuple(a.role for a in actants)))
            return ActRelationCandidate("IS-A", act_ref, ActantRole.SUBJECT, ActantRole.STATE)

    classifier = Classifier()
    result = PerceptionResult(
        source_text="semantics only",
        assertions=(_classification_assertion("A1", "Kripl", "AI"),),
    )
    completed = GoalSemanticService(classifier).complete(result)
    assert completed.act_relations == (
        ActRelationCandidate("IS-A", "A1", ActantRole.SUBJECT, ActantRole.STATE),
    )
    assert classifier.calls == [
        ("semantics only", "A1", (ActantRole.SUBJECT, ActantRole.STATE))
    ]


def test_adaptive_act_relation_probe_is_fixed_choice_and_uid_free():
    from ah.config import LLMRoleSettings
    from ah.llm.process_backend import LLMResponse
    from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

    class Backend:
        def __init__(self):
            self.prompts = []
        def generate(self, prompt, *, system="", override=None, role="generic"):
            self.prompts.append((prompt, system, override, role))
            return LLMResponse("R1", {})

    backend = Backend()
    parser = AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=Path(__file__).resolve().parents[1] / "prompts" / "perception",
            generation=LLMRoleSettings(max_new_tokens=8, temperature=0.0, top_p=1.0, top_k=0),
            retry_attempts=0,
            morphology_backend="none",
            verify_predicate_symbol=False,
        ),
    )
    assertion = _classification_assertion("A1", "Kripl", "AI")
    relation = parser.classify_act_relation(
        "Kripl is AI", "A1", assertion.predicate, assertion.actants
    )
    assert relation == ActRelationCandidate(
        "IS-A", "A1", ActantRole.SUBJECT, ActantRole.STATE
    )
    assert len(backend.prompts) == 1
    prompt, _system, _override, role = backend.prompts[0]
    assert role == "perception_act_relation"
    assert "CHOICES:" in prompt and "NONE" in prompt and "R1" in prompt
    assert "UID" not in prompt


def test_orchestrator_exact_kripl_request_reaches_is_a_reasoner_via_semantics_only():
    from ah.agent.orchestrator import AgentOrchestrator
    from ah.config import ContextSettings, IgnitionSettings, OrchestratorSettings, WorkspaceSettings
    from ah.ignition import IgnitionEngine
    from ah.inference import InferenceMaterializer, QueryGoalBuilder
    from ah.perception import TextSensoryService
    from ah.projection import ContextProjector

    core, context, integration, engine = _runtime()
    kripl = core.add_entity(Domain.C, properties={"name": Property("name", "Крипл", "str")})
    digital = core.add_entity(Domain.C, properties={"name": Property("name", "цифровой агент", "str")})
    ai = core.add_entity(Domain.C, properties={"name": Property("name", "ИИ", "str")})
    core.add_link("IS-A", core.ref(kripl.uid), core.ref(digital.uid), 0.2)
    core.add_link("IS-A", core.ref(digital.uid), core.ref(ai.uid), 0.2)

    raw = PerceptionResult(
        source_text="Докажи что Крипл - это ИИ",
        assertions=(_classification_assertion("A1", "Крипл", "ИИ"),),
        commands=(_command(),),
        act_dependencies=(ActDependencyCandidate("C1", "A1", ActDependencyKind.SUBORDINATE),),
    )

    class Perception:
        def parse(self, text, interaction_context):
            return raw
        def classify_act_relation(self, source_text, act_ref, predicate, actants):
            # No inspection of the command word: the already parsed A1 roles are the
            # complete input to the bounded semantic relation decision.
            return ActRelationCandidate("IS-A", act_ref, ActantRole.SUBJECT, ActantRole.STATE)
        def resolve_template_sense(self, source_text, predicate, filled_roles, role_bindings, options):
            return options[0][0] if len(options) == 1 else None

    class Agent:
        def respond(self, context):
            raise AssertionError("generate_response=False")

    ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
    orchestrator = AgentOrchestrator(
        context=context,
        sensory=TextSensoryService(core),
        perception=Perception(),
        integration=integration,
        ignition=ignition,
        query_builder=QueryGoalBuilder(core),
        inference=engine,
        materializer=InferenceMaterializer(core, IntegrationSettings()),
        projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
        agent=Agent(),
        settings=OrchestratorSettings(auto_materialize_inference=False),
        persistence=None,
    )
    turn = orchestrator.handle_user_text(
        "Докажи что Крипл - это ИИ", generate_response=False
    )
    assert len(turn.queries) == 1
    execution = turn.queries[0]
    assert execution.outcome is not None
    assert execution.outcome.status is LogicalStatus.PROVED
    assert execution.outcome.logical_depth == 2
    assert execution.diagnostics == ("semantic:embedded_relation:IS-A",)
    assert core.store.find_link("IS-A", kripl.uid, ai.uid) is None
