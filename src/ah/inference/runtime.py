from __future__ import annotations

from dataclasses import dataclass, field

from ah.model import Ref

from .attention import InferenceAttention
from .contracts import (
    CognitiveEventKind,
    CognitiveTraceEvent,
    GoalSpec,
    LogicalStatus,
    StopReason,
)


@dataclass(slots=True)
class GoalRuntime:
    """Runtime cognition coordinator for one inference request.

    The object is deliberately non-canonical. It records the causal order
    GoalSpec -> focus -> narrow memory query -> rule/subgoal -> termination and
    delegates every focus shift to the normal Ignition attention boundary.
    """

    goal_spec: GoalSpec
    attention: InferenceAttention | None = None
    events: list[CognitiveTraceEvent] = field(default_factory=list)
    current_workspace: tuple[Ref, ...] = ()

    def begin(self, workspace_refs: tuple[Ref, ...] = ()) -> None:
        self.events.clear()
        self.current_workspace = tuple(workspace_refs)
        if self.attention is not None:
            self.attention.begin()
        self.events.append(
            CognitiveTraceEvent(
                CognitiveEventKind.GOAL_START,
                detail=f"mode={self.goal_spec.mode.value}; target={type(self.goal_spec.target).__name__}",
                workspace_refs=self.current_workspace,
            )
        )

    def focus(self, ref: Ref, *, logical_depth: int, reason: str = "proof focus") -> tuple[Ref, ...]:
        if self.attention is not None:
            self.current_workspace = tuple(
                self.attention.focus(ref, logical_depth=logical_depth)
            )
        self.events.append(
            CognitiveTraceEvent(
                CognitiveEventKind.FOCUS,
                logical_depth=logical_depth,
                ref=ref,
                detail=reason,
                workspace_refs=self.current_workspace,
            )
        )
        return self.current_workspace

    def memory_query(
        self,
        query_kind: str,
        query_key: str,
        *,
        logical_depth: int,
        focus_ref: Ref | None = None,
        candidate_count: int | None = None,
        detail: str = "",
    ) -> None:
        self.events.append(
            CognitiveTraceEvent(
                CognitiveEventKind.MEMORY_QUERY,
                logical_depth=logical_depth,
                ref=focus_ref,
                query_kind=query_kind,
                query_key=query_key,
                candidate_count=candidate_count,
                detail=detail,
                workspace_refs=self.current_workspace,
            )
        )

    def subgoal(self, *, logical_depth: int, detail: str, ref: Ref | None = None) -> None:
        self.events.append(
            CognitiveTraceEvent(
                CognitiveEventKind.SUBGOAL,
                logical_depth=logical_depth,
                ref=ref,
                detail=detail,
                workspace_refs=self.current_workspace,
            )
        )

    def rule(self, rule_id: str, *, logical_depth: int, detail: str = "") -> None:
        self.events.append(
            CognitiveTraceEvent(
                CognitiveEventKind.RULE_SELECTED,
                logical_depth=logical_depth,
                rule_id=rule_id,
                detail=detail,
                workspace_refs=self.current_workspace,
            )
        )

    def finish(self, status: LogicalStatus, stop_reason: StopReason, *, logical_depth: int) -> None:
        self.events.append(
            CognitiveTraceEvent(
                CognitiveEventKind.GOAL_STOP,
                logical_depth=logical_depth,
                detail=f"{status.value}/{stop_reason.value}",
                workspace_refs=self.current_workspace,
            )
        )

    def snapshot(self) -> tuple[CognitiveTraceEvent, ...]:
        return tuple(self.events)
