from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from ah.agent.interaction_context import InteractionContext
from ah.agent.llm_agent import LLMAgent, LLMAgentSettings
from ah.agent.orchestrator import AgentOrchestrator
from ah.config import AppConfig
from ah.core import AHCore, JsonPersistence
from ah.diagnostics import GraphInspector, RuntimeDiagnostics
from ah.dsl import DSLInterpreter
from ah.ignition import IgnitionClock, IgnitionEngine
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.correction import RefutationCommit, SemanticCorrectionService
from ah.integration.contracts import IntegrationCommit
from ah.inference import InferenceEngine, InferenceMaterializer, QueryGoalBuilder
from ah.llm import LocalLLMProcessBackend
from ah.model import Domain, Property, SemanticEntity
from ah.perception import (
    LLMPerceptionService,
    LLMPerceptionSettings,
    PerceptionResult,
    TextSensoryService,
)
from ah.projection import ContextProjector


@dataclass(slots=True)
class RuntimeServices:
    config: AppConfig
    operation_lock: RLock
    core: AHCore
    context: InteractionContext
    integration: IntegrationService
    ignition: IgnitionEngine
    clock: IgnitionClock
    inference: InferenceEngine
    materializer: InferenceMaterializer
    query_builder: QueryGoalBuilder
    projector: ContextProjector
    sensory: TextSensoryService
    persistence: JsonPersistence
    dsl: DSLInterpreter
    correction: SemanticCorrectionService
    graph_inspector: GraphInspector
    diagnostics: RuntimeDiagnostics
    llm: LocalLLMProcessBackend | None
    perception: LLMPerceptionService | None
    agent: LLMAgent | None

    @classmethod
    def build(cls, config: AppConfig, *, core: AHCore | None = None) -> "RuntimeServices":
        persistence = JsonPersistence(config.paths.persistence_file, config.persistence)
        loaded_snapshot = None
        loaded_context = None

        if (
            core is None
            and config.persistence.enabled
            and config.persistence.load_on_start
            and persistence.exists()
        ):
            bundle = persistence.load()
            core = bundle.core
            loaded_snapshot = bundle.ignition_snapshot
            loaded_context = bundle.interaction_context

        core = core or AHCore()
        context = loaded_context or InteractionContext()
        cls._ensure_identity_context(core, context, config)

        operation_lock = RLock()
        integration = IntegrationService(core, IntegrationConfig.from_settings(config.integration))
        ignition = IgnitionEngine(core, config.ignition, config.workspace, config.lifecycle)
        if loaded_snapshot is not None:
            ignition.restore_snapshot(loaded_snapshot)
        clock = IgnitionClock(
            ignition,
            config.ignition.tick_interval_seconds,
            on_tick=lambda _result: persistence.maybe_autosave(
                core, ignition=ignition, context=context
            ),
            execution_lock=operation_lock,
        )
        inference = InferenceEngine(core, config.inference)
        materializer = InferenceMaterializer(core, config.integration)
        query_builder = QueryGoalBuilder(core)
        projector = ContextProjector(core, config.context)
        sensory = TextSensoryService(core)
        dsl = DSLInterpreter(core)
        correction = SemanticCorrectionService(core)
        graph_inspector = GraphInspector(core, ignition)
        diagnostics = RuntimeDiagnostics(core, ignition)

        llm = LocalLLMProcessBackend(config) if config.llm.enabled else None
        perception = (
            LLMPerceptionService(
                llm,
                LLMPerceptionSettings(
                    system_prompt_path=config.paths.perception_prompt_path,
                    generation=config.llm.perception,
                    protocol=config.llm.perception_protocol,
                    probe_prompt_dir=config.paths.perception_prompt_dir,
                    probe_retry_attempts=config.llm.perception_probe_retry_attempts,
                    failure_policy=config.llm.perception_failure_policy,
                    ground_actants=config.llm.perception_ground_actants,
                    max_acts=config.llm.perception_max_acts,
                    max_actants_per_act=config.llm.perception_max_actants_per_act,
                    predicate_symbol_language=config.llm.perception_predicate_symbol_language,
                ),
            )
            if llm is not None
            else None
        )
        agent = (
            LLMAgent(
                llm,
                LLMAgentSettings(
                    config.paths.agent_prompt_path,
                    config.llm.agent,
                    repair_attempts=config.llm.agent_repair_attempts,
                    sanitize_context_echo=config.llm.agent_sanitize_context_echo,
                ),
            )
            if llm is not None
            else None
        )

        return cls(
            config=config,
            operation_lock=operation_lock,
            core=core,
            context=context,
            integration=integration,
            ignition=ignition,
            clock=clock,
            inference=inference,
            materializer=materializer,
            query_builder=query_builder,
            projector=projector,
            sensory=sensory,
            persistence=persistence,
            dsl=dsl,
            correction=correction,
            graph_inspector=graph_inspector,
            diagnostics=diagnostics,
            llm=llm,
            perception=perception,
            agent=agent,
        )

    @staticmethod
    def _ensure_identity_context(core: AHCore, context: InteractionContext, config: AppConfig) -> None:
        def find_role(role: str) -> SemanticEntity | None:
            for element in core.store.elements(Domain.P):
                if isinstance(element, SemanticEntity) and element.meta.get("identity_role") == role:
                    return element
            return None

        if context.self_ref is None:
            self_entity = find_role("SELF")
            if self_entity is None:
                self_entity = core.add_entity(
                    Domain.P,
                    properties={"name": Property("name", config.identity.agent_name, "str")},
                    meta={"identity_role": "SELF"},
                )
            context.self_ref = core.ref(self_entity.uid)

        if context.user_ref is None:
            user_entity = find_role("USER")
            if user_entity is None:
                user_entity = core.add_entity(
                    Domain.P,
                    properties={"name": Property("name", config.identity.user_name, "str")},
                    meta={"identity_role": "USER"},
                )
            context.user_ref = core.ref(user_entity.uid)

    def apply_config(self, new_config: AppConfig) -> None:
        """Apply hot-safe config to live services.

        Callers are responsible for restarting the LLM/runtime when changing fields
        classified that way by the GUI config editor. Canonical AH state is never
        rebuilt here.
        """
        self.config = new_config
        self.integration.config = IntegrationConfig.from_settings(new_config.integration)
        self.ignition.reconfigure(
            new_config.ignition,
            new_config.workspace,
            new_config.lifecycle,
        )
        self.clock.set_interval(new_config.ignition.tick_interval_seconds)
        self.inference.settings = new_config.inference
        self.materializer.integration = new_config.integration
        self.projector = ContextProjector(self.core, new_config.context)

        # Request-level generation values are read from backend.config on every call.
        if not new_config.llm.enabled:
            if self.llm is not None:
                self.llm.stop()
            self.llm = None
            self.perception = None
            self.agent = None
        else:
            if self.llm is None:
                self.llm = LocalLLMProcessBackend(new_config)
            else:
                self.llm.config = new_config
            self.perception = LLMPerceptionService(
                self.llm,
                LLMPerceptionSettings(
                    system_prompt_path=new_config.paths.perception_prompt_path,
                    generation=new_config.llm.perception,
                    protocol=new_config.llm.perception_protocol,
                    probe_prompt_dir=new_config.paths.perception_prompt_dir,
                    probe_retry_attempts=new_config.llm.perception_probe_retry_attempts,
                    failure_policy=new_config.llm.perception_failure_policy,
                    ground_actants=new_config.llm.perception_ground_actants,
                    max_acts=new_config.llm.perception_max_acts,
                    max_actants_per_act=new_config.llm.perception_max_actants_per_act,
                    predicate_symbol_language=new_config.llm.perception_predicate_symbol_language,
                ),
            )
            self.agent = LLMAgent(
                self.llm,
                LLMAgentSettings(
                    new_config.paths.agent_prompt_path,
                    new_config.llm.agent,
                    repair_attempts=new_config.llm.agent_repair_attempts,
                    sanitize_context_echo=new_config.llm.agent_sanitize_context_echo,
                ),
            )

        # Persistence path/settings are intentionally not swapped hot; the GUI marks
        # those fields RESTART_RUNTIME to avoid writing half a session to two stores.

    def create_orchestrator(self) -> AgentOrchestrator:
        if self.perception is None or self.agent is None:
            raise RuntimeError("LLM is disabled; inject a perception service/agent for orchestration tests")
        return AgentOrchestrator(
            context=self.context,
            sensory=self.sensory,
            perception=self.perception,
            integration=self.integration,
            ignition=self.ignition,
            query_builder=self.query_builder,
            inference=self.inference,
            materializer=self.materializer,
            projector=self.projector,
            agent=self.agent,
            settings=self.config.orchestrator,
            persistence=self.persistence,
            runtime_lock=self.operation_lock,
        )

    def integrate_external(
        self,
        perception: PerceptionResult,
        context: InteractionContext | None = None,
    ) -> IntegrationCommit:
        commit = self.integration.integrate_external(perception, context or self.context)
        self.ignition.apply_seed_requests(commit.activation_seeds)
        self.ignition.apply_refutation_requests(commit.refutations)
        return commit

    def integrate_agent_response(
        self,
        perception: PerceptionResult,
        context: InteractionContext | None = None,
    ) -> IntegrationCommit:
        commit = self.integration.integrate_to_h(perception, context or self.context)
        self.ignition.apply_seed_requests(commit.activation_seeds)
        self.ignition.apply_refutation_requests(commit.refutations)
        return commit

    def refute(self, ref) -> RefutationCommit:
        commit = self.correction.refute(ref)
        self.ignition.apply_seed_requests(commit.activation_seeds)
        self.ignition.apply_refutation_requests(commit.refutations)
        return commit

    def start(self) -> None:
        if self.llm is not None and not self.llm.is_running:
            self.llm.start()
        self.clock.start()

    def stop(self, *, save: bool = True) -> None:
        self.clock.stop()
        if save and self.config.persistence.enabled:
            self.save()
        if self.llm is not None:
            self.llm.stop()

    def save(self) -> None:
        self.persistence.save(self.core, ignition=self.ignition, context=self.context)
