from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import Ref, RefKind

if TYPE_CHECKING:
    from ah.ignition import IgnitionEngine


@dataclass(frozen=True, slots=True)
class AttentionFocusEvent:
    """One explicit inference-attention shift executed through Ignition.

    The event is runtime diagnostics only. It is not a proof step and is never
    materialized in AH/H. ``QUERY_RECALL`` is used deliberately: focusing a node is
    attention, not external confirmation of the proposition.
    """

    ref: Ref
    logical_depth: int
    tick: int
    excitation_before: float
    excitation_after: float
    workspace_after: tuple[Ref, ...]


class InferenceAttention(Protocol):
    """Runtime boundary used by the read-only reasoner before semantic expansion."""

    def begin(self) -> None: ...

    def focus(self, ref: Ref, *, logical_depth: int) -> tuple[Ref, ...]: ...


class IgnitionInferenceAttention:
    """Move inference focus by stimulating the current proposition via Ignition.

    The reasoner itself still owns no excitation state and performs no canonical
    writes. It only asks this coordinator to establish attention before expanding a
    proposition. The coordinator schedules a normal QUERY_RECALL seed and executes
    one synchronous causal tick without manufacturing pacemaker time.
    """

    def __init__(self, ignition: IgnitionEngine) -> None:
        self.ignition = ignition
        self._events: list[AttentionFocusEvent] = []

    @property
    def events(self) -> tuple[AttentionFocusEvent, ...]:
        return tuple(self._events)

    def begin(self) -> None:
        self._events.clear()

    def focus(self, ref: Ref, *, logical_depth: int) -> tuple[Ref, ...]:
        if ref.kind is RefKind.L:
            raise ValueError("L has no excitation state and cannot be an inference focus")
        if not self.ignition.core.store.has_uid(ref.uid):
            raise KeyError(ref.uid)

        before = self.ignition.core.store.runtime_state(ref.uid).excitation
        self.ignition.apply_seed_requests(
            (ActivationSeedRequest(ref, SeedReason.QUERY_RECALL),)
        )
        tick_result = self.ignition.tick(include_pacemaker=False)
        after = self.ignition.core.store.runtime_state(ref.uid).excitation
        workspace = self.ignition.workspace_refs()
        self._events.append(
            AttentionFocusEvent(
                ref=ref,
                logical_depth=logical_depth,
                tick=tick_result.tick,
                excitation_before=before,
                excitation_after=after,
                workspace_after=workspace,
            )
        )
        return workspace
