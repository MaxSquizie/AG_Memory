from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
from ah.agent.orchestrator import AgentOrchestrator
from ah.config import (
    ContextSettings,
    IgnitionSettings,
    InferenceSettings,
    IntegrationSettings,
    OrchestratorSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.diagnostics import ProofSnapshotBuilder
from ah.ignition import IgnitionEngine
from ah.inference import InferenceEngine, InferenceMaterializer, QueryBuildResult, QueryGoalBuilder
from ah.integration import IntegrationConfig, IntegrationService, TemplateCompletionService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActantCandidate,
    AssertionCandidate,
    CommandCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
    TextSensoryService,
)
from ah.projection import ContextProjector


PROJECT = Path(__file__).resolve().parents[1]


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
    integration = IntegrationService(
        core, IntegrationConfig.from_settings(IntegrationSettings())
    )
    return core, context, integration


def _polar_query(predicate: PredicateCandidate) -> QueryCandidate:
    return QueryCandidate(
        predicate,
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Крипл"),
            ActantCandidate(ActantRole.STATE, mention="ИИ"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )


def test_structural_predicate_with_multiple_role_compatible_templates_requests_bounded_sense():
    core, _context, integration = _runtime()
    symbol = core.add_abstract_symbol({"be"})
    first = core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.STATE)
    )
    second = core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.STATE)
    )
    predicate = PredicateCandidate(
        surface="это",
        normalized_hint="be",
        sense_hint="IMPLICIT",
    )
    result = PerceptionResult(
        source_text="Крипл - это ИИ?",
        queries=(_polar_query(predicate),),
    )

    requests = integration.template_requests(result)
    assert len(requests) == 1
    request = requests[0]
    assert [item.template_uid for item in request.sense_options] == [first.uid, second.uid]
    assert all("UID" not in item.description for item in request.sense_options)

    class Perception:
        def __init__(self):
            self.calls = 0

        def resolve_template_sense(
            self, source_text, predicate, filled_roles, role_bindings, options
        ):
            self.calls += 1
            assert [label for label, _description in options] == ["C1", "C2"]
            return "C2"

    perception = Perception()
    completed = TemplateCompletionService(integration, perception).complete(result)
    assert perception.calls == 1
    assert completed.queries[0].predicate.template_selection is not None
    assert completed.queries[0].predicate.template_selection.existing_template_uid == second.uid


def test_unresolved_epistemic_goal_is_fail_closed_instead_of_answering_from_active_memory():
    core, context, integration = _runtime()

    query = _polar_query(
        PredicateCandidate(
            "это",
            "be",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        )
    )
    result = PerceptionResult(source_text="Крипл - это ИИ?", queries=(query,))

    class Perception:
        def parse(self, text, interaction_context):
            return result

        def propose_template_candidate(self, source_text, predicate, filled_roles, role_bindings=()):
            return predicate.template_candidate

        def classify_act_relation(self, source_text, act_ref, predicate, actants):
            return None

    class NeverBuildGoal:
        def build(self, query, interaction_context):
            return QueryBuildResult(None, ("forced_unresolved_goal",))

    class Agent:
        def __init__(self):
            self.respond_calls = 0

        def respond(self, agent_context):
            self.respond_calls += 1
            return "Да, Крипл — это ИИ."

    agent = Agent()
    ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
    orchestrator = AgentOrchestrator(
        context=context,
        sensory=TextSensoryService(core),
        perception=Perception(),
        integration=integration,
        ignition=ignition,
        query_builder=NeverBuildGoal(),
        inference=InferenceEngine(core, InferenceSettings()),
        materializer=InferenceMaterializer(core, IntegrationSettings()),
        projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
        agent=agent,
        settings=OrchestratorSettings(),
        persistence=None,
    )

    turn = orchestrator.handle_user_text("Крипл - это ИИ?", generate_response=True)
    assert len(turn.queries) == 1
    assert turn.queries[0].outcome is None
    assert turn.queries[0].diagnostics == ("forced_unresolved_goal",)
    assert agent.respond_calls == 0
    assert "не удалось построить формальную цепочку вывода" in turn.response_text
    assert "UNRESOLVED" in turn.agent_context.rendered
    assert "ACTIVE MEMORY не является доказательством" in turn.agent_context.rendered


def test_unresolved_proof_obligation_has_first_class_explorer_snapshot():
    core, _context, _integration = _runtime()
    proof = ProofSnapshotBuilder(core).build_unresolved(
        chain_id="live:1",
        source="LIVE",
        title="Крипл - это ИИ?",
        diagnostics=("template_not_unique",),
    )
    assert proof.status == "UNRESOLVED"
    assert proof.stop_reason == "GOAL_NOT_COMPILED"
    assert proof.logical_depth == 0
    assert proof.trace_uids == ()
    assert proof.diagnostics == ("template_not_unique",)
    assert "Доказательство не запускалось" in proof.conclusion_text


def test_gui_records_unresolved_live_goal_in_inference_explorer():
    main = (PROJECT / "src/ah/gui/main_window.py").read_text(encoding="utf-8")
    assert "build_unresolved(" in main
    assert '"status": "UNRESOLVED"' in main
    assert '"stop_reason": "GOAL_NOT_COMPILED"' in main


def test_polar_query_mode_no_longer_delegates_exists_vs_fill_role_to_llm():
    parser = (PROJECT / "src/ah/perception/adaptive_parser.py").read_text(encoding="utf-8")
    assert 'self._probe(\n                            "query_mode"' not in parser
    assert "query_mode = QueryMode.EXISTS" in parser


def test_polar_kripl_query_with_structural_template_ambiguity_produces_direct_proof_chain():
    core, context, integration = _runtime()
    kripl = core.add_entity(
        Domain.C, properties={"name": Property("name", "Крипл", "str")}
    )
    ai = core.add_entity(
        Domain.C, properties={"name": Property("name", "ИИ", "str")}
    )
    symbol = core.add_abstract_symbol({"be"})
    _other = core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.STATE)
    )
    factual = core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.STATE)
    )
    fact, _created = core.add_hypernode(
        Domain.C,
        core.ref(factual.uid),
        {ActantRole.SUBJECT: core.ref(kripl.uid), ActantRole.STATE: core.ref(ai.uid)},
        0.4,
    )

    query = _polar_query(
        PredicateCandidate("это", "be", sense_hint="IMPLICIT")
    )
    raw = PerceptionResult(source_text="Крипл - это ИИ?", queries=(query,))

    class Perception:
        def parse(self, text, interaction_context):
            return raw

        def resolve_template_sense(
            self, source_text, predicate, filled_roles, role_bindings, options
        ):
            # Local labels only; the fake perception never receives canonical UIDs.
            assert len(options) == 2
            return "C2"

        def classify_act_relation(self, source_text, act_ref, predicate, actants):
            # Even if the bounded IS-A classifier declines the relation, exact
            # proposition evidence must still go through ExistsGoal/proof rather
            # than letting the agent answer from ACTIVE MEMORY.
            return None

    class Agent:
        def respond(self, context):
            return "Да."

    ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
    orchestrator = AgentOrchestrator(
        context=context,
        sensory=TextSensoryService(core),
        perception=Perception(),
        integration=integration,
        ignition=ignition,
        query_builder=QueryGoalBuilder(core),
        inference=InferenceEngine(core, InferenceSettings()),
        materializer=InferenceMaterializer(core, IntegrationSettings()),
        projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
        agent=Agent(),
        settings=OrchestratorSettings(auto_materialize_inference=False),
        persistence=None,
    )

    turn = orchestrator.handle_user_text("Крипл - это ИИ?", generate_response=False)
    assert len(turn.queries) == 1
    execution = turn.queries[0]
    assert execution.outcome is not None
    assert execution.outcome.status.value == "PROVED"
    assert fact.uid in [ref.uid for ref in execution.outcome.uid_trace]
    proof = ProofSnapshotBuilder(core).build(
        execution.outcome,
        chain_id="live:kripl",
        source="LIVE",
        title="Крипл - это ИИ?",
    )
    assert proof.status == "PROVED"
    assert proof.stop_reason == "GOAL_SATISFIED"
    assert proof.trace_uids == (fact.uid,)
    assert [step.rule for step in proof.steps] == ["DIRECT_FACT"]



def test_query_experience_is_preserved_in_h_but_projected_as_non_fact():
    core, context, integration = _runtime()
    query = _polar_query(
        PredicateCandidate(
            "это", "be",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        )
    )
    commit = integration.integrate_external(
        PerceptionResult(source_text="Крипл - это ИИ?", queries=(query,)),
        context,
    )
    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert tuple(event.meta.get("speech_act_kinds") or ()) == ("QUERY",)

    projected = ContextProjector(core, ContextSettings(max_tokens=4096)).project(
        "Что я спрашивал?", (commit.experience_ref,), ()
    )
    assert "задал вопрос (НЕ ФАКТ)" in projected.rendered
    assert "Крипл - это ИИ?" in projected.rendered
    assert "Ранее пользователь сказал" not in projected.rendered


def test_embedded_command_target_cannot_reenter_active_memory_as_asserted_evidence():
    core, context, integration = _runtime()
    target = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "это", "be",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Крипл"),
            ActantCandidate(ActantRole.STATE, mention="ИИ"),
        ),
    )
    command = CommandCandidate(
        PredicateCandidate("проверь", "check", template_candidate=TemplateCandidate(())),
        local_id="C1",
    )
    commit = integration.integrate_external(
        PerceptionResult(
            source_text="Проверь утверждение: Крипл - это ИИ",
            assertions=(target,),
            commands=(command,),
            act_dependencies=(
                ActDependencyCandidate("C1", "A1", ActDependencyKind.SUBORDINATE),
            ),
        ),
        context,
    )
    embedded = next(item for item in commit.assertions if item.local_id == "A1")
    assert embedded.semantic_scope == "EMBEDDED"
    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert tuple(event.meta.get("speech_act_kinds") or ()) == ("COMMAND",)

    projected = ContextProjector(core, ContextSettings(max_tokens=4096)).project(
        "Что было раньше?", (embedded.ref, commit.experience_ref), ()
    )
    assert "запрос/команду (НЕ ФАКТ)" in projected.rendered
    assert "Пользователь ранее сказал" not in projected.rendered
    assert projected.rendered.count("Крипл - это ИИ") == 1
