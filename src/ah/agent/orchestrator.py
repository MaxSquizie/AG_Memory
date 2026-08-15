from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from typing import Protocol
from threading import RLock

from ah.agent.interaction_context import InteractionContext
from ah.config import OrchestratorSettings
from ah.core.persistence import JsonPersistence
from ah.ignition import IgnitionEngine, TickResult
from ah.inference import InferenceEngine, InferenceMaterializer, QueryGoalBuilder
from ah.inference.contracts import InferenceOutcome
from ah.inference.materialization import MaterializationResult
from ah.integration import IntegrationError, IntegrationService
from ah.integration.contracts import IntegrationCommit
from ah.perception import PerceptionParseError, PerceptionResult, TextSensoryResult, TextSensoryService
from ah.projection import ContextProjector
from ah.projection.contracts import AgentContext


class PerceptionService(Protocol):
    def parse(self, text: str, interaction_context: InteractionContext) -> PerceptionResult: ...


class ResponseAgent(Protocol):
    def respond(self, context: AgentContext) -> str: ...


@dataclass(frozen=True, slots=True)
class QueryExecution:
    outcome: InferenceOutcome | None
    materialization: MaterializationResult | None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    user_text: str
    sensory: TextSensoryResult
    perception: PerceptionResult
    integration: IntegrationCommit
    ticks_after_input: tuple[TickResult, ...]
    queries: tuple[QueryExecution, ...]
    agent_context: AgentContext
    response_text: str | None
    response_perception: PerceptionResult | None
    response_integration: IntegrationCommit | None
    ticks_after_response: tuple[TickResult, ...]
    autosaved: bool


class AgentOrchestrator:
    """One complete external turn following Архитектура_v3 §22.

    The orchestrator owns sequencing only. Semantic decisions remain in Perception,
    Integration, Ignition, Inference and Projection modules.
    """

    def __init__(
        self,
        *,
        context: InteractionContext,
        sensory: TextSensoryService,
        perception: PerceptionService,
        integration: IntegrationService,
        ignition: IgnitionEngine,
        query_builder: QueryGoalBuilder,
        inference: InferenceEngine,
        materializer: InferenceMaterializer,
        projector: ContextProjector,
        agent: ResponseAgent,
        settings: OrchestratorSettings,
        persistence: JsonPersistence | None = None,
        runtime_lock: RLock | None = None,
    ) -> None:
        self.context = context
        self.sensory = sensory
        self.perception = perception
        self.integration = integration
        self.ignition = ignition
        self.query_builder = query_builder
        self.inference = inference
        self.materializer = materializer
        self.projector = projector
        self.agent = agent
        self.settings = settings
        self.persistence = persistence
        self.runtime_lock = runtime_lock

    def _record_raw_external_experience(self, text: str, lock) -> None:
        with lock:
            failed_turn = self.integration.integrate_external(
                PerceptionResult(source_text=text), self.context
            )
            self.ignition.apply_seed_requests(failed_turn.activation_seeds)

    def handle_user_text(self, text: str, *, generate_response: bool = True) -> AgentTurnResult:
        lock = self.runtime_lock or nullcontext()

        # Memory mutations/reads are short critical sections. The expensive LLM
        # calls stay outside the lock so a continuously running IgnitionClock can
        # keep ticking while the model is thinking, but it cannot observe a
        # half-integrated canonical transaction.
        with lock:
            self.ignition.begin_prompt_epoch()
            sensory = self.sensory.process(text)
            self.ignition.apply_seed_requests(sensory.activation_seeds)

        try:
            perception = self.perception.parse(text, self.context)
        except PerceptionParseError:
            # Semantic failure never erases the fact that the external communication
            # happened. Preserve only its raw H experience and re-raise the original
            # parse error; no failed semantic candidate is committed.
            self._record_raw_external_experience(text, lock)
            raise

        try:
            with lock:
                integration = self.integration.integrate_external(perception, self.context)
                self.ignition.apply_seed_requests(integration.activation_seeds)
                self.ignition.apply_refutation_requests(integration.refutations)
        except IntegrationError:
            # Validation/canonicalization can reject an otherwise completed
            # PerceptionResult. The source turn is still an experienced H event,
            # exactly as for a perception failure, while the failed semantic
            # transaction remains rolled back.
            self._record_raw_external_experience(text, lock)
            raise

        with lock:
            input_ticks = tuple(self.ignition.tick() for _ in range(self.settings.ticks_after_input))
            workspace = self.ignition.workspace_refs()

            query_results: list[QueryExecution] = []
            inference_outcomes: list[InferenceOutcome] = []
            for query in integration.unresolved_queries:
                built = self.query_builder.build(query, self.context)
                if built.goal is None:
                    query_results.append(QueryExecution(None, None, built.diagnostics))
                    continue
                outcome = self.inference.solve(built.goal, workspace)
                inference_outcomes.append(outcome)
                materialized = (
                    self.materializer.materialize(outcome)
                    if self.settings.auto_materialize_inference
                    else None
                )
                query_results.append(QueryExecution(outcome, materialized, built.diagnostics))

            agent_context = self.projector.project(text, workspace, tuple(inference_outcomes))

        response_text: str | None = None
        response_perception: PerceptionResult | None = None
        response_integration: IntegrationCommit | None = None
        response_ticks: tuple[TickResult, ...] = ()

        if generate_response:
            response_text = self.agent.respond(agent_context)

            # Every actual agent utterance is experienced in H.  Diagnostics may
            # deliberately stop at AgentContext; in that mode no synthetic agent
            # utterance is invented merely to satisfy the normal interaction path.
            if self.settings.parse_agent_response_to_h:
                response_perception = self.perception.parse(response_text, self.context)
            else:
                response_perception = PerceptionResult(
                    source_text=response_text,
                    assertions=(),
                    queries=(),
                    commands=(),
                    diagnostics=("AGENT_H_TEXT_ONLY",),
                )
            with lock:
                response_integration = self.integration.integrate_to_h(response_perception, self.context)
                self.ignition.apply_seed_requests(response_integration.activation_seeds)
                self.ignition.apply_refutation_requests(response_integration.refutations)
                response_ticks = tuple(
                    self.ignition.tick() for _ in range(self.settings.ticks_after_response)
                )

        with lock:
            autosaved = False
            if self.persistence is not None:
                autosaved = self.persistence.maybe_autosave(
                    self.integration.core,
                    ignition=self.ignition,
                    context=self.context,
                )

        return AgentTurnResult(
            user_text=text,
            sensory=sensory,
            perception=perception,
            integration=integration,
            ticks_after_input=input_ticks,
            queries=tuple(query_results),
            agent_context=agent_context,
            response_text=response_text,
            response_perception=response_perception,
            response_integration=response_integration,
            ticks_after_response=response_ticks,
            autosaved=autosaved,
        )
