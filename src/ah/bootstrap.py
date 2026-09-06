from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from threading import RLock

from ah.agent.interaction_context import InteractionContext
from ah.agent.llm_agent import LLMAgent, LLMAgentSettings
from ah.agent.orchestrator import AgentOrchestrator
from ah.config import AppConfig, PersistenceSettings
from ah.core import AHCore, JsonPersistence
from ah.diagnostics import GraphInspector, RuntimeDiagnostics
from ah.diagnostics.session_log import audit_tick_result
from ah.dsl import DSLInterpreter
from ah.ignition import IgnitionClock, IgnitionEngine
from ah.ignition.engine import IgnitionSnapshot
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.correction import RefutationCommit, SemanticCorrectionService
from ah.integration.contracts import IntegrationCommit
from ah.inference import InferenceEngine, InferenceMaterializer, QueryGoalBuilder, InferenceSchemaRegistry
from ah.llm import LLMBackend, build_llm_backend
from ah.model import Domain, Property, SemanticEntity
from ah.perception import (
    LLMPerceptionService,
    LLMPerceptionSettings,
    PerceptionResult,
    TextSensoryService,
    build_morphology,
)
from ah.projection import ContextProjector


@dataclass(slots=True)
class RuntimeServices:
    config: AppConfig
    operation_lock: RLock
    core: AHCore
    context: InteractionContext
    integration: IntegrationService
    schema_registry: InferenceSchemaRegistry
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
    llm: LLMBackend | None
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
        schema_registry = InferenceSchemaRegistry.default()
        integration = IntegrationService(
            core,
            IntegrationConfig.from_settings(config.integration),
            schema_registry=schema_registry,
        )
        ignition = IgnitionEngine(core, config.ignition, config.workspace, config.lifecycle)
        if loaded_snapshot is not None:
            ignition.restore_snapshot(loaded_snapshot)
        def _on_tick(result):
            audit_tick_result(result)
            persistence.maybe_autosave(core, ignition=ignition, context=context)

        clock = IgnitionClock(
            ignition,
            config.ignition.tick_interval_seconds,
            on_tick=_on_tick,
            execution_lock=operation_lock,
        )
        inference = InferenceEngine(core, config.inference, schema_registry=schema_registry)
        materializer = InferenceMaterializer(core, config.integration)
        query_builder = QueryGoalBuilder(core)
        projector = ContextProjector(core, config.context)
        sensory = TextSensoryService(core, build_morphology(config.llm.perception_morphology_backend))
        dsl = DSLInterpreter(core)
        correction = SemanticCorrectionService(core)
        graph_inspector = GraphInspector(core, ignition, runtime_lock=operation_lock)
        diagnostics = RuntimeDiagnostics(core, ignition, runtime_lock=operation_lock)

        llm = build_llm_backend(config)
        perception = (
            LLMPerceptionService(
                llm,
                LLMPerceptionSettings(
                    system_prompt_path=config.paths.perception_prompt_path,
                    generation=config.llm.perception,
                    protocol=config.llm.perception_protocol,
                    probe_prompt_dir=config.paths.perception_prompt_dir,
                    probe_retry_attempts=config.llm.perception_probe_retry_attempts,
                    ground_actants=config.llm.perception_ground_actants,
                    max_actants_per_act=config.llm.perception_max_actants_per_act,
                    predicate_symbol_language=config.llm.perception_predicate_symbol_language,
                    morphology_backend=config.llm.perception_morphology_backend,
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
                    context_max_tokens=config.context.max_tokens,
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
            schema_registry=schema_registry,
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
                self.llm = build_llm_backend(new_config)
            else:
                expected_backend_type = {
                    "builtin_process": "LocalLLMProcessBackend",
                    "ollama": "OllamaBackend",
                    "lmstudio": "LMStudioBackend",
                }[new_config.llm.backend]
                if type(self.llm).__name__ != expected_backend_type:
                    self.llm.stop()
                    self.llm = build_llm_backend(new_config)
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
                    ground_actants=new_config.llm.perception_ground_actants,
                    max_actants_per_act=new_config.llm.perception_max_actants_per_act,
                    predicate_symbol_language=new_config.llm.perception_predicate_symbol_language,
                    morphology_backend=new_config.llm.perception_morphology_backend,
                ),
            )
            self.agent = LLMAgent(
                self.llm,
                LLMAgentSettings(
                    new_config.paths.agent_prompt_path,
                    new_config.llm.agent,
                    repair_attempts=new_config.llm.agent_repair_attempts,
                    sanitize_context_echo=new_config.llm.agent_sanitize_context_echo,
                    context_max_tokens=new_config.context.max_tokens,
                ),
            )

        # Persistence path/settings are intentionally not swapped hot; the GUI marks
        # those fields RESTART_RUNTIME to avoid writing half a session to two stores.

    def tune_decay(
        self,
        *,
        alpha: float,
        midpoint_ticks: float,
        reactivation_min_input: float | None = None,
        resolved_symbol_seed: float | None = None,
    ) -> None:
        """Apply operator-facing decay controls immediately without resetting memory.

        Current x, decay origin and age are preserved. reactivation_min_input is
        hot-tunable as well because it is part of the decay-epoch reset policy,
        not a restart-only structural setting.
        """
        decay = replace(
            self.config.ignition.decay,
            alpha=float(alpha),
            midpoint_ticks=float(midpoint_ticks),
            reactivation_min_input=(
                self.config.ignition.decay.reactivation_min_input
                if reactivation_min_input is None
                else float(reactivation_min_input)
            ),
        )
        seeds = self.config.ignition.seeds
        if resolved_symbol_seed is not None:
            seeds = replace(seeds, resolved_symbol=float(resolved_symbol_seed))
        ignition = replace(self.config.ignition, decay=decay, seeds=seeds)
        self.config = replace(self.config, ignition=ignition)
        self.ignition.reconfigure_decay(decay)
        self.ignition.reconfigure_seed_levels(seeds)


    def tune_ignition_mechanism(
        self,
        *,
        pacemaker_enabled: bool | None = None,
        pacemaker_pulse: float | None = None,
        workspace_threshold: float | None = None,
    ) -> None:
        """Hot-swap pacemaker amplitude/enabled state and Workspace threshold.

        Note that architectural pacemaker frequency is ``ignition.nu``; pulse
        amplitude is a separate seed parameter and is intentionally named so.
        """
        ignition = self.config.ignition
        workspace = self.config.workspace
        if pacemaker_enabled is not None:
            ignition = replace(ignition, pacemaker=replace(ignition.pacemaker, enabled=bool(pacemaker_enabled)))
        if pacemaker_pulse is not None:
            ignition = replace(ignition, seeds=replace(ignition.seeds, pacemaker=max(0.0, float(pacemaker_pulse))))
        if workspace_threshold is not None:
            workspace = replace(workspace, threshold=max(0.0, float(workspace_threshold)))
        self.config = replace(self.config, ignition=ignition, workspace=workspace)
        self.ignition.reconfigure(ignition, workspace, self.config.lifecycle)
        self.clock.set_interval(ignition.tick_interval_seconds)

    def import_corpus(self, path: str | Path, *, domain: Domain = Domain.C, save: bool = True, cold_save: bool = True):
        from ah.corpus import import_corpus_file
        with self.operation_lock:
            result = import_corpus_file(self.core, Path(path), default_domain=domain)
            if save:
                self._save_import_result(cold_save=cold_save)
        return result

    def import_raw_text(self, text: str, *, save: bool = True, parse_user_semantics: bool = True, cold_save: bool = True, strict: bool = True):
        from ah.corpus import import_raw_experience, split_raw_experience_text
        with self.operation_lock:
            result = import_raw_experience(self, split_raw_experience_text(text), parse_user_semantics=parse_user_semantics, strict=strict)
            if save:
                self._save_import_result(cold_save=cold_save)
        return result

    def import_dialogue(self, source, *, save: bool = True, parse_user_semantics: bool = True, cold_save: bool = True, strict: bool = True):
        from ah.corpus import import_dialogue_cold, load_dialogue_file, parse_dialogue_json
        turns = load_dialogue_file(source) if isinstance(source, (str, Path)) else parse_dialogue_json(source)
        with self.operation_lock:
            result = import_dialogue_cold(self, turns, parse_user_semantics=parse_user_semantics, strict=strict)
            if save:
                self._save_import_result(cold_save=cold_save)
        return result

    def import_memory(self, path: str | Path, *, save: bool = True, cold_restore: bool = True):
        from ah.corpus import import_memory_snapshot
        with self.operation_lock:
            result = import_memory_snapshot(self, path, cold_restore=cold_restore)
            if save:
                self._save_import_result(cold_save=cold_restore)
        return result

    def _save_import_result(self, *, cold_save: bool) -> None:
        if cold_save:
            JsonPersistence(
                self.persistence.path,
                PersistenceSettings(
                    enabled=True,
                    load_on_start=True,
                    autosave_every_ticks=self.config.persistence.autosave_every_ticks,
                    save_runtime_state=False,
                    save_pending_impulses=False,
                ),
            ).save(self.core, context=self.context)
        else:
            self.save()

    def reset_memory(self, *, persist: bool = True) -> None:
        """Reset canonical AH/runtime/context while preserving service wiring."""
        with self.operation_lock:
            was_running = self.clock.running
            if was_running:
                self.clock.stop()
            self.core.store.replace_from(AHCore().store)
            fresh_context = InteractionContext()
            self._ensure_identity_context(self.core, fresh_context, self.config)
            for item in fields(InteractionContext):
                setattr(self.context, item.name, getattr(fresh_context, item.name))
            self.ignition.restore_snapshot(IgnitionSnapshot(0, {}, {}))
            self.projector = ContextProjector(self.core, self.config.context)
            if persist and self.config.persistence.enabled:
                self._save_import_result(cold_save=True)
            if was_running:
                self.clock.start()

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
