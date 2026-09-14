from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime

from ah.association import AssociationCoordinator, AssociationOutcome, AssociationStatus
from ah.inference import AssociationQueryBuildResult, InferenceOutcome, TurnGoalBuilder
from ah.inference.contracts import (
    ExistingRefConclusion,
    GoalMode,
    GoalSpec,
    LogicalStatus,
    ProofSupport,
    StopReason,
)
from ah.model import Ref, RefKind
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
    """One runtime goal execution.

    ``association_outcome`` remains the authoritative associative result.  ``outcome``
    may additionally contain a diagnostic M2-visible proof *of convergence* so the
    operator can audit whether an association was actually found.  That diagnostic
    proof is never fed back into ordinary logical inference/projection and therefore
    does not promote associative convergence to semantic entailment.
    """

    association_outcome: AssociationOutcome | None = None


class AgentOrchestrator(_BaseAgentOrchestrator):
    """AgentOrchestrator extension routing AssociationGoal to AssociationCoordinator.

    The mature base pipeline still owns parsing, Integration, settling, discourse,
    logical inference, response recording and persistence. This extension reuses one
    no-response base pass, executes only the association requests that the typed
    GoalCompiler marked, then rebuilds AgentContext with an explicit ASSOCIATION
    RESULTS section.  For diagnostics it also freezes a proof-shaped convergence
    trace in ``QueryExecution.outcome``; that trace proves only that both bounded
    activation fronts met at one canonical representation, not that a new factual
    proposition follows from the meeting point.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.association = AssociationCoordinator(self.integration.core, self.ignition)
        self.association_projector = AssociationContextProjector(
            self.integration.core, self.projector.settings
        )

    def _association_uid_trace(self, outcome: AssociationOutcome) -> tuple[Ref, ...]:
        """Freeze canonical provenance used by an association convergence.

        Search-only MEMORY_QUERY hops may name a canonical incidence object in
        ``via_uid``.  Include it when it still exists so the GUI can overlay the
        exact route on the live canvas.  Runtime-only query edges themselves are not
        invented as L nodes.
        """

        refs: list[Ref] = []
        seen: set[str] = set()

        def add(ref: Ref) -> None:
            if ref.uid in seen or not self.integration.core.store.has_uid(ref.uid):
                return
            seen.add(ref.uid)
            refs.append(ref)

        for path in (outcome.left_path, outcome.right_path):
            if path is None:
                continue
            for index, ref in enumerate(path.refs):
                add(ref)
                if index >= len(path.hops):
                    continue
                via_uid = path.hops[index].via_uid
                if not via_uid or via_uid in seen:
                    continue
                if self.integration.core.store.has_uid(via_uid):
                    add(self.integration.core.ref(via_uid))
        if outcome.common_ref is not None:
            add(outcome.common_ref)
        return tuple(refs)

    @staticmethod
    def _association_stop_reason(outcome: AssociationOutcome) -> StopReason:
        if outcome.status is AssociationStatus.FOUND:
            return StopReason.GOAL_SATISFIED
        if outcome.status is AssociationStatus.DEPTH_EXHAUSTED:
            return StopReason.DEPTH_EXHAUSTED
        if outcome.status is AssociationStatus.BUDGET_EXHAUSTED:
            return StopReason.BUDGET_EXHAUSTED
        if outcome.status is AssociationStatus.RESOURCE_LIMIT:
            return StopReason.RESOURCE_LIMIT
        return StopReason.SEARCH_EXHAUSTED

    def _association_diagnostic_outcome(
        self, outcome: AssociationOutcome
    ) -> InferenceOutcome:
        """Represent association search as an auditable M2 diagnostic obligation.

        ``PROVED`` here means exactly "the runtime ASSOCIATION goal reached its stop
        condition by convergence".  It is deliberately tagged with
        ``GoalMode.ASSOCIATION`` and ``ASSOCIATION_CONVERGENCE`` support, excluded
        from ordinary inference projection below, and never materialized into AH.
        """

        found = outcome.found
        conclusion = (
            ExistingRefConclusion(outcome.common_ref)
            if found and outcome.common_ref is not None
            else None
        )
        depth = max(
            outcome.left_path.depth if outcome.left_path is not None else 0,
            outcome.right_path.depth if outcome.right_path is not None else 0,
        )
        diagnostics = (
            f"semantic:association_status:{outcome.status.value}",
            "runtime:association_convergence_proof:not_semantic_entailment",
            f"runtime:association_common_candidates:{len(outcome.common_candidates)}",
            f"runtime:association_minimal_fact_count:{outcome.minimal_fact_count}",
        )
        support = (
            ProofSupport(
                premise_refs=(outcome.goal.left, outcome.goal.right),
                rule_id="ASSOCIATION_CONVERGENCE",
                relation_id="ASSOCIATION",
            ),
        ) if found else ()
        return InferenceOutcome(
            status=LogicalStatus.PROVED if found else LogicalStatus.UNKNOWN,
            stop_reason=self._association_stop_reason(outcome),
            conclusion=conclusion,
            premise_refs=(outcome.goal.left, outcome.goal.right),
            uid_trace=self._association_uid_trace(outcome),
            conclusion_domain=(
                self.integration.core.store.domain_of(outcome.common_ref.uid)
                if outcome.common_ref is not None
                else None
            ),
            expanded_states=outcome.expanded_states,
            diagnostics=diagnostics,
            goal_spec=GoalSpec(outcome.goal, mode=GoalMode.ASSOCIATION),
            logical_depth=depth,
            proof_support=support,
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
                diagnostic_outcome = self._association_diagnostic_outcome(outcome)
                executions.append(
                    QueryExecution(
                        diagnostic_outcome,
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
        # then routed through its dedicated activation coordinator rather than being
        # allowed to masquerade as an ordinary semantic RelationGoal.
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
                and getattr(execution, "association_outcome", None) is None
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

        # The base no-response pass already attempted persistence for the user
        # turn. Repeat it only if this extension changed runtime/canonical state:
        # association advances Ignition and a recorded response adds an H event.
        # A failed response with no association must not duplicate an identical
        # persistence write.
        post_route_changed = bool(association_outcomes) or response_integration is not None
        post_autosaved = self._autosave(lock) if post_route_changed else False
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
