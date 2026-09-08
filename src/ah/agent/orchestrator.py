from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import nullcontext
from datetime import datetime
from typing import Callable, Protocol
import re
from threading import RLock

from ah.agent.interaction_context import InteractionContext
from ah.agent.discourse import DiscourseRelationRefiner
from ah.config import OrchestratorSettings
from ah.core.persistence import JsonPersistence
from ah.ignition import IgnitionEngine, TickResult
from ah.inference import (
    IgnitionInferenceAttention,
    InferenceEngine,
    InferenceMaterializer,
    QueryGoalBuilder,
    TurnGoalBuilder,
)
from ah.inference.contracts import InferenceOutcome
from ah.inference.materialization import MaterializationResult
from ah.integration import IntegrationError, IntegrationService, TemplateCompletionService
from ah.integration.contracts import (
    ActivationSeedRequest, ClarificationRequest, ClarificationResolutionCommit,
    IntegrationCommit, SeedReason,
)
from ah.perception import (
    DiscourseRelationDecision,
    PerceptionParseError,
    PerceptionClarificationRequired,
    PerceptionResult,
    PredicateCandidate,
    GoalSemanticService,
    apply_speech_act_scoping,
    TemplateCandidate,
    TemplateSelection,
    TextSensoryResult,
    TextSensoryService,
)
from ah.projection import ContextProjector
from ah.projection.contracts import AgentContext, AgentContextDiagnostic


class PerceptionService(Protocol):
    def parse(self, text: str, interaction_context: InteractionContext) -> PerceptionResult: ...

    def propose_template_candidate(
        self,
        source_text: str,
        predicate,
        filled_roles,
        role_bindings=(),
    ) -> TemplateCandidate: ...

    def resolve_template_sense(
        self,
        source_text: str,
        predicate: PredicateCandidate,
        filled_roles,
        role_bindings,
        options: tuple[tuple[str, str], ...],
    ) -> str | None: ...

    def interpret_clarification_answer(
        self, answer_text: str, option_labels: tuple[str, ...]
    ) -> int | None: ...

    def parse_with_structural_resolution(
        self, text: str, interaction_context: InteractionContext, resolution_key: str
    ) -> PerceptionResult: ...

    def classify_discourse_relation(
        self,
        narrative_context: str,
        prior_events: tuple[str, ...],
        current_events: tuple[str, ...],
        *,
        excluded_pairs: tuple[tuple[int, int], ...] = (),
    ) -> DiscourseRelationDecision | None: ...


class ResponseAgent(Protocol):
    def respond(self, context: AgentContext) -> str: ...

    def clarify(self, request: ClarificationRequest) -> str: ...


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
    clarification_request: ClarificationRequest | None = None
    clarification_resolution: ClarificationResolutionCommit | None = None
    agent_context_diagnostic: AgentContextDiagnostic | None = None


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
        turn_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.context = context
        self.sensory = sensory
        self.perception = perception
        self.integration = integration
        self.ignition = ignition
        self.query_builder = query_builder
        self.inference = inference
        self.inference_attention = IgnitionInferenceAttention(ignition)
        self.materializer = materializer
        self.projector = projector
        self.discourse = DiscourseRelationRefiner(integration, perception, projector)
        self.agent = agent
        self.settings = settings
        self.persistence = persistence
        self.runtime_lock = runtime_lock
        self.turn_clock = turn_clock or (lambda: datetime.now().astimezone())

    def _settle_input_wave(self) -> tuple[TickResult, ...]:
        """Drain the current prompt's causal wave before freezing Workspace.

        A resolved lexical mention starts at S. With synchronous one-edge-per-tick
        propagation, one old post-input tick only reaches T; the proposition N would
        still be pending when AgentContext is built. The configured settling ticks
        therefore run before projection. They do not schedule fresh pacemaker pulses,
        so a single user turn cannot inject multiple seconds of ν background noise.
        """
        return tuple(
            self.ignition.tick(include_pacemaker=False)
            for _ in range(self.settings.ticks_after_input)
        )

    def _record_raw_external_experience(
        self,
        text: str,
        lock,
        *,
        source_timestamp: datetime,
    ) -> IntegrationCommit:
        with lock:
            failed_turn = self.integration.integrate_external(
                PerceptionResult(source_text=text),
                self.context,
                source_timestamp=source_timestamp,
            )
            self.ignition.apply_seed_requests(failed_turn.activation_seeds)
            return failed_turn

    @staticmethod
    def _apply_template_resolutions(result, candidates, selections):
        return TemplateCompletionService.apply_resolutions(result, candidates, selections)

    def _complete_dynamic_templates(self, result: PerceptionResult, lock) -> PerceptionResult:
        # Public reusable implementation; lock protects the canonical T snapshot.
        with lock:
            service = TemplateCompletionService(self.integration, self.perception)
            return service.complete(result)

    @staticmethod
    def _normalize_clarification_text(text: str) -> str:
        return re.sub(r"[^\wёЁ]+", " ", text.casefold(), flags=re.UNICODE).strip()

    @classmethod
    def _deterministic_clarification_selection(
        cls, text: str, request: ClarificationRequest
    ) -> int | None:
        normalized = cls._normalize_clarification_text(text)
        if not normalized:
            return None
        if normalized.isdigit():
            index = int(normalized)
            if 1 <= index <= len(request.options):
                return index
        matches: list[int] = []
        padded = f" {normalized} "
        for option in request.options:
            labels = [option.label]
            if " (" in option.label:
                labels.append(option.label.split(" (", 1)[0])
            normalized_labels = [cls._normalize_clarification_text(label) for label in labels]
            if any(
                label and (normalized == label or f" {label} " in padded)
                for label in normalized_labels
            ):
                matches.append(option.index)
        return matches[0] if len(matches) == 1 else None

    def _clarification_selection(
        self, text: str, request: ClarificationRequest
    ) -> int | None:
        """Return one explicit clarification choice, or ``None`` for an unrelated turn.

        Pending clarification is dialogue state, not a global input mode.  A new user
        utterance may answer it, but an utterance that does not explicitly identify
        one option must continue through ordinary perception instead of being trapped
        behind the old ambiguity.
        """
        selected_index = self._deterministic_clarification_selection(text, request)
        if selected_index is not None:
            return selected_index
        interpreter = getattr(self.perception, "interpret_clarification_answer", None)
        if callable(interpreter):
            interpreted = interpreter(text, tuple(option.label for option in request.options))
            if isinstance(interpreted, int) and 1 <= interpreted <= len(request.options):
                return interpreted
        return None

    def _generate_clarification(self, request: ClarificationRequest) -> str:
        clarify = getattr(self.agent, "clarify", None)
        if callable(clarify):
            return str(clarify(request)).strip()
        labels = ", ".join(option.label for option in request.options)
        return f"Уточните, кого или что означает «{request.mention}»: {labels}?"

    @staticmethod
    def _unresolved_goal_response(text: str) -> str:
        if re.search(r"[А-Яа-яЁё]", text):
            return (
                "Не могу подтвердить это по памяти: для текущей цели не удалось "
                "построить формальную цепочку вывода, поэтому содержательный ответ "
                "из ACTIVE MEMORY не выдаю."
            )
        return (
            "I cannot establish this from memory: no formal proof goal could be "
            "compiled for the current target, so I will not answer from ACTIVE MEMORY alone."
        )

    def _enqueue_clarifications(self, requests: tuple[ClarificationRequest, ...]) -> None:
        known = {ref.uid for ref in self.context.pending_clarification_refs}
        for request in requests:
            if request.ambiguous_ref.uid not in known:
                self.context.pending_clarification_refs.append(request.ambiguous_ref)
                known.add(request.ambiguous_ref.uid)

    def _next_pending_clarification(self) -> ClarificationRequest | None:
        while self.context.pending_clarification_refs:
            ref = self.context.pending_clarification_refs[0]
            try:
                return self.integration.clarification_request(ref)
            except IntegrationError:
                self.context.pending_clarification_refs.pop(0)
        return None

    def _record_agent_utterance(
        self, response_text: str, lock
    ) -> tuple[PerceptionResult, IntegrationCommit, tuple[TickResult, ...]]:
        if self.settings.parse_agent_response_to_h:
            response_perception = self.perception.parse(response_text, self.context)
            response_perception = self._complete_dynamic_templates(response_perception, lock)
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
                self.ignition.tick(include_pacemaker=False)
                for _ in range(self.settings.ticks_after_response)
            )
        return response_perception, response_integration, response_ticks

    def _autosave(self, lock) -> bool:
        with lock:
            if self.persistence is None:
                return False
            return self.persistence.maybe_autosave(
                self.integration.core,
                ignition=self.ignition,
                context=self.context,
            )

    def _handle_clarification_answer(
        self,
        text: str,
        *,
        request: ClarificationRequest,
        selected_index: int,
        generate_response: bool,
        lock,
        source_timestamp: datetime,
    ) -> AgentTurnResult:
        with lock:
            self.ignition.begin_prompt_epoch()
            sensory = self.sensory.process(text)
            self.ignition.apply_seed_requests(sensory.activation_seeds)

        perception = PerceptionResult(
            source_text=text,
            diagnostics=("CLARIFICATION_ANSWER",),
        )
        resolution: ClarificationResolutionCommit | None = None
        structural_result: PerceptionResult | None = None
        structural_experience_ref = None
        selected = request.options[selected_index - 1] if selected_index is not None else None

        if selected is not None and request.kind == "STRUCTURAL":
            with lock:
                source_text, resolution_key, structural_experience_ref = (
                    self.integration.structural_clarification_selection(
                        request.ambiguous_ref, selected.ref
                    )
                )
            parser = getattr(self.perception, "parse_with_structural_resolution", None)
            if not callable(parser):
                raise PerceptionParseError("Perception service cannot resolve structural clarification")
            structural_result = parser(source_text, self.context, resolution_key)
            structural_result = self._complete_dynamic_templates(structural_result, lock)
            structural_result = apply_speech_act_scoping(structural_result)
            structural_result = GoalSemanticService(self.perception).complete(structural_result)

        with lock:
            if selected is not None:
                if request.kind == "STRUCTURAL":
                    assert structural_result is not None and structural_experience_ref is not None
                    delayed = self.integration.integrate_external_resolution(
                        structural_result, self.context, structural_experience_ref
                    )
                    self.ignition.apply_seed_requests(delayed.activation_seeds)
                    self.ignition.apply_refutation_requests(delayed.refutations)
                    resolution = self.integration.finalize_structural_clarification(
                        request.ambiguous_ref, selected.ref
                    )
                else:
                    resolution = self.integration.resolve_clarification(
                        request.ambiguous_ref, selected.ref
                    )
                    self.ignition.apply_seed_requests(resolution.activation_seeds)
                if (
                    self.context.pending_clarification_refs
                    and self.context.pending_clarification_refs[0] == request.ambiguous_ref
                ):
                    self.context.pending_clarification_refs.pop(0)
                else:
                    self.context.pending_clarification_refs = [
                        ref for ref in self.context.pending_clarification_refs
                        if ref != request.ambiguous_ref
                    ]

            # The user's clarification utterance is still an H experience. It is
            # not promoted to a standalone C/P assertion such as M("Мария").
            integration = self.integration.integrate_external(
                perception,
                self.context,
                source_timestamp=source_timestamp,
            )
            self.ignition.apply_seed_requests(integration.activation_seeds)
            input_ticks = self._settle_input_wave()
            workspace = self.ignition.workspace_refs()
            next_request = self._next_pending_clarification()
            agent_context = self.projector.project(text, workspace, ())
            agent_context_diagnostic = self.projector.diagnose(
                agent_context,
                tick_index=self.ignition.tick_index,
                workspace_threshold=self.ignition.workspace_settings.threshold,
                settle_ticks=len(input_ticks),
            )

        response_text: str | None = None
        response_perception: PerceptionResult | None = None
        response_integration: IntegrationCommit | None = None
        response_ticks: tuple[TickResult, ...] = ()
        active_request = next_request if resolution is not None else request
        if generate_response:
            if active_request is not None:
                response_text = self._generate_clarification(active_request)
            else:
                response_text = self.agent.respond(agent_context)
            response_perception, response_integration, response_ticks = self._record_agent_utterance(
                response_text, lock
            )

        autosaved = self._autosave(lock)
        return AgentTurnResult(
            user_text=text,
            sensory=sensory,
            perception=perception,
            integration=integration,
            ticks_after_input=input_ticks,
            queries=(),
            agent_context=agent_context,
            agent_context_diagnostic=agent_context_diagnostic,
            response_text=response_text,
            response_perception=response_perception,
            response_integration=response_integration,
            ticks_after_response=response_ticks,
            autosaved=autosaved,
            clarification_request=active_request,
            clarification_resolution=resolution,
        )

    def handle_user_text(
        self,
        text: str,
        *,
        generate_response: bool = True,
        source_timestamp: datetime | None = None,
    ) -> AgentTurnResult:
        lock = self.runtime_lock or nullcontext()
        # Capture one timezone-aware source anchor for the complete external turn.
        # It resolves only explicit relative temporal expressions; Integration does
        # not copy it into facts that have no TIME role.
        turn_timestamp = source_timestamp or self.turn_clock()
        if turn_timestamp.tzinfo is None or turn_timestamp.utcoffset() is None:
            raise ValueError("source_timestamp must be timezone-aware")

        if self.context.pending_clarification_refs:
            with lock:
                pending_request = self._next_pending_clarification()
            if pending_request is not None:
                selected_index = self._clarification_selection(text, pending_request)
                if selected_index is not None:
                    return self._handle_clarification_answer(
                        text,
                        request=pending_request,
                        selected_index=selected_index,
                        generate_response=generate_response,
                        lock=lock,
                        source_timestamp=turn_timestamp,
                    )
                # The utterance does not answer the pending choice.  Keep the
                # unresolved K in dialogue state, but process this input normally.

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
            perception = self._complete_dynamic_templates(perception, lock)
            perception = apply_speech_act_scoping(perception)
            perception = GoalSemanticService(self.perception).complete(perception)
        except PerceptionClarificationRequired as exc:
            # Genuine structural ambiguity is not an error and must not be guessed.
            # Record the external utterance in H, persist only the pending structural
            # choice in H dialogue state, and return an explicit clarification path.
            raw_commit = self._record_raw_external_experience(
                text, lock, source_timestamp=turn_timestamp
            )
            with lock:
                request = self.integration.register_structural_clarification(
                    exc.spec, raw_commit.experience_ref
                )
                # Diagnostic/no-response turns surface the clarification contract but
                # must not arm dialogue state: acceptance executes independent cases
                # sequentially with generate_response=False. Live dialogue state is
                # armed only when the clarification is actually presented to the user.
                if generate_response:
                    self._enqueue_clarifications((request,))
                integration = replace(
                    raw_commit,
                    clarification_required=True,
                    clarifications=(request,),
                )
                input_ticks = self._settle_input_wave()
                workspace = self.ignition.workspace_refs()
                agent_context = self.projector.project(text, workspace, ())
                agent_context_diagnostic = self.projector.diagnose(
                    agent_context,
                    tick_index=self.ignition.tick_index,
                    workspace_threshold=self.ignition.workspace_settings.threshold,
                    settle_ticks=len(input_ticks),
                )

            response_text: str | None = None
            response_perception: PerceptionResult | None = None
            response_integration: IntegrationCommit | None = None
            response_ticks: tuple[TickResult, ...] = ()
            if generate_response:
                response_text = self._generate_clarification(request)
                response_perception, response_integration, response_ticks = self._record_agent_utterance(
                    response_text, lock
                )
            autosaved = self._autosave(lock)
            return AgentTurnResult(
                user_text=text,
                sensory=sensory,
                perception=PerceptionResult(
                    source_text=text, diagnostics=("STRUCTURAL_CLARIFICATION_REQUIRED",)
                ),
                integration=integration,
                ticks_after_input=input_ticks,
                queries=(),
                agent_context=agent_context,
                agent_context_diagnostic=agent_context_diagnostic,
                response_text=response_text,
                response_perception=response_perception,
                response_integration=response_integration,
                ticks_after_response=response_ticks,
                autosaved=autosaved,
                clarification_request=request,
            )
        except PerceptionParseError:
            # Semantic failure never erases the fact that the external communication
            # happened. Preserve only its raw H experience and re-raise the original
            # parse error; no failed semantic candidate is committed.
            self._record_raw_external_experience(
                text, lock, source_timestamp=turn_timestamp
            )
            raise

        try:
            with lock:
                integration = self.integration.integrate_external(
                    perception,
                    self.context,
                    source_timestamp=turn_timestamp,
                )
                self.ignition.apply_seed_requests(integration.activation_seeds)
                self.ignition.apply_refutation_requests(integration.refutations)
        except IntegrationError:
            # Validation/canonicalization can reject an otherwise completed
            # PerceptionResult. The source turn is still an experienced H event,
            # exactly as for a perception failure, while the failed semantic
            # transaction remains rolled back.
            self._record_raw_external_experience(
                text, lock, source_timestamp=turn_timestamp
            )
            raise

        with lock:
            # Query reference resolution happens before the turn-local ignition tick.
            # A relational description such as ``моего друга`` may traverse an
            # already canonical support fact (USER + ДРУГ -> N_ЕСТЬ -> МИША).
            # The resolved referent and that support N are attention anchors only:
            # no fact is created and h_N confirmation is not triggered.
            # Evidence retrieval is driven by turn semantics, never lexical intent
            # markers. Direct queries and propositions scoped EMBEDDED under any
            # QUERY/COMMAND root become inference goals automatically.
            identity_attention_refs = tuple(self.ignition.workspace_refs())
            built_requests = list(
                TurnGoalBuilder(self.integration.core, self.query_builder).build(
                    integration, self.context, perception,
                    attention_refs=identity_attention_refs,
                )
            )
            attention: dict[str, object] = {}
            for built in built_requests:
                for ref in built.attention_refs:
                    attention[ref.uid] = ref
            if attention:
                self.ignition.apply_seed_requests(
                    tuple(
                        ActivationSeedRequest(ref, SeedReason.QUERY_RECALL)
                        for ref in attention.values()
                    )
                )

            input_ticks = self._settle_input_wave()
            workspace = self.ignition.workspace_refs()

            discourse_review = self.discourse.prepare(integration, workspace, text)

        # Cross-turn semantic probes follow the same trust boundary as primary
        # Perception: never hold the canonical runtime lock while waiting on the
        # language model.  The review is an immutable snapshot containing only
        # UID-free semantics on the model-facing side; canonical refs stay local.
        discourse_decisions = self.discourse.decide(discourse_review)

        with lock:
            discourse_relations = self.discourse.integrate(
                discourse_review, discourse_decisions
            )
            if discourse_relations:
                integration = replace(
                    integration,
                    relations=integration.relations + discourse_relations,
                )
            # L has no excitation field, so Workspace membership is unchanged by
            # the relation write. Re-read it nevertheless to preserve one canonical
            # snapshot boundary before inference.
            workspace = self.ignition.workspace_refs()

            query_results: list[QueryExecution] = []
            inference_outcomes: list[InferenceOutcome] = []
            for built in built_requests:
                if built.goal is None:
                    query_results.append(QueryExecution(None, None, built.diagnostics))
                    continue
                outcome = self.inference.solve(
                    built.goal,
                    workspace,
                    attention=self.inference_attention,
                )
                # Inference attention is real Ignition activity. Re-freeze Workspace
                # after each proof because the next query and AgentContext must see
                # the state that actually exists after the attention shift.
                workspace = self.ignition.workspace_refs()
                inference_outcomes.append(outcome)
                materialized = (
                    self.materializer.materialize(outcome)
                    if self.settings.auto_materialize_inference
                    else None
                )
                query_results.append(QueryExecution(outcome, materialized, built.diagnostics))

            unresolved_goal_diagnostics = tuple(
                execution.diagnostics
                for execution in query_results
                if execution.outcome is None
            )
            agent_context = self.projector.project(
                text,
                workspace,
                tuple(inference_outcomes),
                unresolved_goal_diagnostics,
            )
            agent_context_diagnostic = self.projector.diagnose(
                agent_context,
                tick_index=self.ignition.tick_index,
                workspace_threshold=self.ignition.workspace_settings.threshold,
                settle_ticks=len(input_ticks),
            )

        response_text: str | None = None
        response_perception: PerceptionResult | None = None
        response_integration: IntegrationCommit | None = None
        response_ticks: tuple[TickResult, ...] = ()

        clarification_request = integration.clarifications[0] if integration.clarifications else None
        if generate_response:
            if integration.clarifications:
                response_text = self._generate_clarification(clarification_request)
            elif any(execution.outcome is None for execution in query_results):
                # A semantic proof obligation exists but deterministic compilation
                # failed. ACTIVE MEMORY may contain suggestive prose/H experiences,
                # but letting the response LLM answer from it would recreate the
                # black-box path the proof system is meant to eliminate. Fail closed
                # and expose the compiler failure through diagnostics/Proof Explorer.
                response_text = self._unresolved_goal_response(text)
            else:
                response_text = self.agent.respond(agent_context)
            response_perception, response_integration, response_ticks = self._record_agent_utterance(
                response_text, lock
            )
            if integration.clarifications:
                # Arm the dialogue state only after the clarification utterance was
                # successfully generated and committed as an H experience.
                with lock:
                    self._enqueue_clarifications(integration.clarifications)

        autosaved = self._autosave(lock)

        return AgentTurnResult(
            user_text=text,
            sensory=sensory,
            perception=perception,
            integration=integration,
            ticks_after_input=input_ticks,
            queries=tuple(query_results),
            agent_context=agent_context,
            agent_context_diagnostic=agent_context_diagnostic,
            response_text=response_text,
            response_perception=response_perception,
            response_integration=response_integration,
            ticks_after_response=response_ticks,
            autosaved=autosaved,
            clarification_request=clarification_request,
            clarification_resolution=None,
        )
