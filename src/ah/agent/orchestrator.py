from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime

from ah.association import AssociationCoordinator, AssociationOutcome
from ah.inference import AssociationQueryBuildResult, InferenceOutcome, TurnGoalBuilder
from ah.projection.association_context import AssociationContextProjector

from .orchestrator_base import (
    AgentOrchestrator as _BaseAgentOrchestrator,
    AgentTurnResult,
    PerceptionService,
    QueryExecution as _BaseQueryExecution,
    ResponseAgent,
)


@dataclass(frozen=True, slots=True)
class QueryExecution(_BaseQueryExecution):
    """One runtime goal execution; association is explicitly non-inferential."""

    association_outcome: AssociationOutcome | None = None


class AgentOrchestrator(_BaseAgentOrchestrator):
    """AgentOrchestrator extension routing AssociationGoal to AssociationCoordinator.

    The mature base pipeline still owns parsing, Integration, settling, discourse,
    logical inference, response recording and persistence. This extension reuses one
    no-response base pass, executes only the association requests that the typed
    GoalCompiler marked, then rebuilds AgentContext with an explicit non-proof
    ASSOCIATION RESULTS section before optional response generation.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.association = AssociationCoordinator(self.integration.core, self.ignition)
        self.association_projector = AssociationContextProjector(
            self.integration.core, self.projector.settings
        )

    def _execute_associations(
        self,
        result: AgentTurnResult,
    ) -> tuple[
        tuple[QueryExecution | _BaseQueryExecution, ...],
        tuple[AssociationOutcome, ...],
        tuple[tuple[str, ...], ...],
    ]:
        attention_refs = tuple(self.ignition.workspace_refs())
        built_requests = tuple(
            TurnGoalBuilder(self.integration.core, self.query_builder).build(
                result.integration,
                self.context,
                result.perception,
                attention_refs=attention_refs,
            )
        )
        if len(built_requests) != len(result.queries):
            raise RuntimeError(
                "association post-route lost GoalCompiler/result ordering: "
                f"built={len(built_requests)} executed={len(result.queries)}"
            )

        executions: list[QueryExecution | _BaseQueryExecution] = []
        association_outcomes: list[AssociationOutcome] = []
        unresolved: list[tuple[str, ...]] = []

        for built, previous in zip(built_requests, result.queries):
            if isinstance(built, AssociationQueryBuildResult):
                if built.association_goal is None:
                    execution = QueryExecution(
                        None,
                        None,
                        built.diagnostics,
                        association_outcome=None,
                    )
                    executions.append(execution)
                    unresolved.append(built.diagnostics)
                    continue

                outcome = self.association.solve(built.association_goal)
                association_outcomes.append(outcome)
                executions.append(
                    QueryExecution(
                        None,
                        None,
                        built.diagnostics
                        + (f"semantic:association_status:{outcome.status.value}",),
                        association_outcome=outcome,
                    )
                )
                continue

            executions.append(previous)
            if previous.outcome is None:
                unresolved.append(previous.diagnostics)

        return tuple(executions), tuple(association_outcomes), tuple(unresolved)

    def handle_user_text(
        self,
        text: str,
        *,
        generate_response: bool = True,
        source_timestamp: datetime | None = None,
    ) -> AgentTurnResult:
        # Suppress only presentation in the base pass. Canonical user semantics and
        # ordinary inference are committed/executed exactly once. Association is
        # then routed through its dedicated activation coordinator rather than M2.
        base = super().handle_user_text(
            text,
            generate_response=False,
            source_timestamp=source_timestamp,
        )
        lock = self.runtime_lock or nullcontext()

        with lock:
            executions, association_outcomes, unresolved = self._execute_associations(base)
            workspace = self.ignition.workspace_refs()
            inference_outcomes = tuple(
                execution.outcome
                for execution in executions
                if isinstance(execution.outcome, InferenceOutcome)
            )
            agent_context = self.association_projector.project_with_associations(
                text,
                workspace,
                inference_outcomes,
                unresolved,
                association_outcomes,
            )
            agent_context_diagnostic = self.association_projector.diagnose(
                agent_context,
                tick_index=self.ignition.tick_index,
                workspace_threshold=self.ignition.workspace_settings.threshold,
                settle_ticks=len(base.ticks_after_input),
            )

        response_text: str | None = None
        response_perception = None
        response_integration = None
        response_ticks = ()
        response_error: str | None = None

        if generate_response:
            if base.clarification_request is not None:
                producer = lambda: self._generate_clarification(
                    base.clarification_request
                )
            elif unresolved:
                producer = lambda: self._unresolved_goal_response(text)
            else:
                producer = lambda: self.agent.respond(agent_context)

            response_text, response_error = self._safe_generate_response(producer)
            if response_text is not None:
                response_perception, response_integration, response_ticks = (
                    self._record_agent_utterance(response_text, lock)
                )
                if base.integration.clarifications:
                    with lock:
                        self._enqueue_clarifications(base.integration.clarifications)

        # The base no-response pass may already have autosaved the user turn. Run
        # the post-route autosave anyway: association changes runtime excitation and
        # a generated response may add a new H occurrence after that first save.
        post_autosaved = self._autosave(lock)
        autosaved = base.autosaved or post_autosaved
        return replace(
            base,
            queries=executions,
            agent_context=agent_context,
            agent_context_diagnostic=agent_context_diagnostic,
            response_text=response_text,
            response_perception=response_perception,
            response_integration=response_integration,
            ticks_after_response=response_ticks,
            autosaved=autosaved,
            response_error=response_error,
        )


__all__ = [
    "AgentOrchestrator",
    "AgentTurnResult",
    "PerceptionService",
    "QueryExecution",
    "ResponseAgent",
]
