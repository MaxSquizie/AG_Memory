from __future__ import annotations

from ah.agent import InteractionContext
from ah.agent.llm_agent import _DEFAULT_AGENT_PROMPT
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
from ah.ignition import IgnitionEngine
from ah.inference import InferenceEngine, InferenceMaterializer, QueryGoalBuilder
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import Domain, Property
from ah.perception import PerceptionResult, TextSensoryService
from ah.projection import ContextProjector


class _Perception:
    def parse(self, text, interaction_context):
        return PerceptionResult(source_text=text)


class _FailingAgent:
    def respond(self, context):
        raise ConnectionError("main llm unavailable")

    def clarify(self, request):
        raise ConnectionError("main llm unavailable")


class _Persistence:
    def __init__(self):
        self.calls = 0

    def maybe_autosave(self, core, *, ignition=None, context=None):
        self.calls += 1
        return True


def _orchestrator():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Агент", "str")}
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")}
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid),
        user_ref=core.ref(user_entity.uid),
    )
    integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    ignition = IgnitionEngine(
        core, IgnitionSettings(), WorkspaceSettings(threshold=0.1)
    )
    persistence = _Persistence()
    orchestrator = AgentOrchestrator(
        context=context,
        sensory=TextSensoryService(core),
        perception=_Perception(),
        integration=integration,
        ignition=ignition,
        query_builder=QueryGoalBuilder(core),
        inference=InferenceEngine(core, InferenceSettings()),
        materializer=InferenceMaterializer(core, IntegrationSettings()),
        projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
        agent=_FailingAgent(),
        settings=OrchestratorSettings(),
        persistence=persistence,
    )
    return core, persistence, orchestrator


def test_main_llm_failure_does_not_rollback_user_occurrence_and_autosave_still_runs():
    core, persistence, orchestrator = _orchestrator()

    turn = orchestrator.handle_user_text("Зафиксируй этот вход.")

    assert turn.integration.experience_ref is not None
    assert core.store.has_uid(turn.integration.experience_ref.uid)
    assert turn.response_text is None
    assert turn.response_perception is None
    assert turn.response_integration is None
    assert turn.ticks_after_response == ()
    assert turn.response_error is not None
    assert turn.response_error.startswith(
        "response_generation_failed:ConnectionError:"
    )
    assert turn.autosaved is True
    assert persistence.calls == 1


def test_main_llm_contract_explicitly_forbids_secondary_memory_requests():
    prompt = _DEFAULT_AGENT_PROMPT.casefold()
    assert "контекст памяти окончателен для этого хода" in prompt
    assert "не проси, не инициируй и не предлагай дополнительный поиск" in prompt
    assert "весь recall выполняется goalspec/reasoner" in prompt
