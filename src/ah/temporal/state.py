from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from ah.core import AHCore, SupportRecord
from ah.model import ActantRole, Domain, FunctionSymbol, Hypernode, Ref, RefKind

from .contracts import TemporalKind, TemporalMode, TemporalValue, TransitionOperator
from .reasoner import _parse_bound
from .storage import ensure_time_entity, temporal_value_from_ref


class StateTruth(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"
    CONFLICTED = "CONFLICTED"


@dataclass(frozen=True, slots=True)
class StateTransitionResult:
    transition_ref: Ref
    state_ref: Ref | None
    negated_state_ref: Ref | None = None
    closed_state_refs: tuple[Ref, ...] = ()


class StateTracker:
    """Explicit state-interval transition semantics for canonical N/g.

    This component is invoked only for already-classified transition occurrences.
    It never guesses whether an arbitrary predicate is a state.
    """

    def __init__(self, core: AHCore, *, default_weight: float = 0.2) -> None:
        self.core = core
        self.default_weight = default_weight

    def _point_order_key(self, time_ref: Ref) -> datetime | None:
        value = temporal_value_from_ref(self.core, time_ref)
        if value is None or value.kind is not TemporalKind.POINT:
            return None
        parsed = _parse_bound(value.start)
        return None if parsed is None else parsed[0]

    def _state_key(self, node: Hypernode) -> tuple:
        return (
            node.template.uid,
            tuple(
                sorted(
                    (role.value, value.kind.value, value.uid)
                    for role, value in node.actants.items()
                    if role is not ActantRole.TIME and isinstance(value, Ref)
                )
            ),
        )

    @staticmethod
    def _is_negated_state(node: Hypernode) -> bool:
        return str(node.meta.get("semantic_scope") or "") == "NEGATED_STATE"

    def _matching_states(
        self,
        prototype: Hypernode,
        *,
        negated: bool | None = None,
    ) -> tuple[Hypernode, ...]:
        """Return state occurrences with the same predicate/actants as prototype.

        Positive P and scoped operand of NOT(P) intentionally share one structural
        state key, but transition semantics must never mistake one polarity for the
        other. ``negated=None`` is used only by truth evaluation where both are
        needed.
        """
        key = self._state_key(prototype)
        out: list[Hypernode] = []
        for node in self.core.store.find_hypernodes_by_template(prototype.template.uid):
            if str(node.meta.get("temporal_mode") or "") != TemporalMode.STATE.value:
                continue
            if self._state_key(node) != key:
                continue
            is_negated = self._is_negated_state(node)
            if negated is not None and is_negated is not negated:
                continue
            out.append(node)
        return tuple(out)

    def _open_interval(self, node: Hypernode) -> tuple[Ref, TemporalValue] | None:
        time_ref = node.actants.get(ActantRole.TIME)
        if not isinstance(time_ref, Ref) or time_ref.kind is not RefKind.M:
            return None
        value = temporal_value_from_ref(self.core, time_ref)
        if value is None or value.kind is not TemporalKind.INTERVAL or value.end is not None:
            return None
        return time_ref, value

    def _close_open_states(
        self,
        prototype: Hypernode,
        point: TemporalValue,
        *,
        negated: bool,
    ) -> tuple[Ref, ...]:
        closed: list[Ref] = []
        point_range = _parse_bound(point.start)
        if point_range is None:
            raise ValueError("State transition requires an orderable TIME point")
        point_key = point_range[0]
        for node in self._matching_states(prototype, negated=negated):
            current = self._open_interval(node)
            if current is None:
                continue
            _old_time_ref, old_value = current
            start_range = _parse_bound(old_value.start)
            if start_range is None:
                raise ValueError("Open state interval has a non-orderable start")
            if point_key < start_range[0]:
                raise ValueError("State transition cannot close an interval before it starts")
            closed_value = TemporalValue(
                TemporalKind.INTERVAL,
                old_value.start,
                point.start,
                old_value.precision,
                old_value.timezone or point.timezone,
                source_text=old_value.source_text,
            )
            new_time_ref, _ = ensure_time_entity(self.core, closed_value)
            domain = self.core.store.domain_of(node.uid)
            assert domain is not None
            updated = replace(node, actants={**dict(node.actants), ActantRole.TIME: new_time_ref})
            self.core.edit_element(domain, updated)
            closed.append(self.core.ref(node.uid))
            # The old open interval may remain as an independently referenced time m;
            # lifecycle/GC owns eventual physical deletion.
        return tuple(closed)

    def _open_states(self, prototype: Hypernode, *, negated: bool) -> tuple[Hypernode, ...]:
        return tuple(
            node
            for node in self._matching_states(prototype, negated=negated)
            if self._open_interval(node) is not None
        )

    def _not_parent(self, node: Hypernode) -> Ref | None:
        for parent in self.core.store.function_parents(node.uid):
            if parent.function_id == "NOT":
                return self.core.ref(parent.uid)
        return None

    def _materialize_state(
        self,
        prototype: Hypernode,
        point: TemporalValue,
        *,
        negated: bool,
    ) -> tuple[Ref, Ref | None]:
        interval = TemporalValue(
            TemporalKind.INTERVAL,
            point.start,
            None,
            point.precision,
            point.timezone,
            source_text=point.source_text,
        )
        time_ref, _ = ensure_time_entity(self.core, interval)
        domain = self.core.store.domain_of(prototype.uid) or Domain.C
        actants = {
            role: value for role, value in prototype.actants.items()
            if role is not ActantRole.TIME
        }
        actants[ActantRole.TIME] = time_ref
        scope = "NEGATED_STATE" if negated else None
        meta = {"temporal_mode": TemporalMode.STATE.value, "state_interval": True}
        if scope is not None:
            meta["semantic_scope"] = scope
        node, _ = self.core.add_hypernode(
            domain,
            prototype.template,
            actants,
            weight=prototype.weight,
            meta=meta,
            count_occurrence=False,
        )
        node_ref = self.core.ref(node.uid)
        if not negated:
            return node_ref, None
        function, _ = self.core.ensure_function(domain, "NOT", (node_ref,))
        return node_ref, self.core.ref(function.uid)

    def _covers(self, value: TemporalValue, point: TemporalValue) -> bool | None:
        """Conservative coverage for a half-open state interval ``[start, end)``.

        A partial POINT such as a day denotes a range of possible instants.  We
        return True only when the whole query range is definitely inside the
        state interval, False only when it is definitely outside, and None when
        coarse precision overlaps a transition boundary.  This prevents an exact
        STOP instant from being counted as both P and NOT(P).
        """
        if value.kind is not TemporalKind.INTERVAL or point.kind is not TemporalKind.POINT:
            return None
        point_range = _parse_bound(point.start)
        start_range = _parse_bound(value.start) if value.start is not None else None
        end_range = _parse_bound(value.end) if value.end is not None else None
        if point_range is None:
            return None
        if value.start is not None and start_range is None:
            return None
        if value.end is not None and end_range is None:
            return None

        q_start, q_end = point_range
        if start_range is not None:
            start_earliest, start_latest = start_range
            if q_end < start_earliest:
                return False
            if q_start < start_latest:
                return None

        if end_range is not None:
            end_earliest, end_latest = end_range
            # end is exclusive.  For an exact instant earliest == latest, so a
            # query at that instant is definitely outside the positive interval.
            if q_start >= end_latest:
                return False
            if q_end >= end_earliest:
                return None

        return True

    def current_truth(self, proposition_ref: Ref, at_time_ref: Ref) -> StateTruth:
        """Evaluate state truth by interval coverage, never by mention recency."""
        if proposition_ref.kind is not RefKind.N:
            raise TypeError("State proposition prototype must be N")
        prototype = self.core.store.get_hypernode(proposition_ref.uid)
        point = temporal_value_from_ref(self.core, at_time_ref)
        if point is None or point.kind is not TemporalKind.POINT:
            return StateTruth.UNKNOWN
        positive = False
        negative = False
        for node in self._matching_states(prototype):
            time_ref = node.actants.get(ActantRole.TIME)
            if not isinstance(time_ref, Ref):
                continue
            interval = temporal_value_from_ref(self.core, time_ref)
            if interval is None or self._covers(interval, point) is not True:
                continue
            scope = str(node.meta.get("semantic_scope") or "")
            if scope == "NEGATED_STATE":
                # Negation is factual only when the scoped operand is actually
                # owned by a canonical NOT expression.
                if any(parent.function_id == "NOT" for parent in self.core.store.function_parents(node.uid)):
                    negative = True
            elif not scope:
                positive = True
        if positive and negative:
            return StateTruth.CONFLICTED
        if positive:
            return StateTruth.POSITIVE
        if negative:
            return StateTruth.NEGATIVE
        return StateTruth.UNKNOWN

    def apply(
        self,
        proposition_ref: Ref,
        operator: TransitionOperator,
        at_time_ref: Ref,
    ) -> StateTransitionResult:
        if proposition_ref.kind is not RefKind.N:
            raise TypeError("State transition proposition must be N")
        prototype = self.core.store.get_hypernode(proposition_ref.uid)
        point = temporal_value_from_ref(self.core, at_time_ref)
        if point is None or point.kind is not TemporalKind.POINT or self._point_order_key(at_time_ref) is None:
            raise ValueError("State transition requires an orderable TIME point")
        domain = self.core.store.domain_of(prototype.uid) or Domain.C
        transition_g, _ = self.core.ensure_function(domain, operator.value, (proposition_ref,))
        transition_ref = self.core.ref(transition_g.uid)

        closed: tuple[Ref, ...] = ()
        state_ref: Ref | None = None
        negated_ref: Ref | None = None
        if operator is TransitionOperator.START:
            if self._open_states(prototype, negated=False):
                raise ValueError("START cannot open a state that is already open")
            # An explicitly represented NOT(P) interval ends when P starts.  This
            # is not an invented intermediate negation; it only closes an already
            # existing negative state.
            self._close_open_states(prototype, point, negated=True)
            state_ref, _ = self._materialize_state(prototype, point, negated=False)
        elif operator is TransitionOperator.STOP:
            closed = self._close_open_states(prototype, point, negated=False)
            if not closed:
                raise ValueError("STOP requires an existing open positive state")
            negative_opens = self._open_states(prototype, negated=True)
            if negative_opens:
                negated_ref = self._not_parent(negative_opens[-1])
            if negated_ref is None:
                _operand_ref, negated_ref = self._materialize_state(prototype, point, negated=True)
        elif operator is TransitionOperator.NO_LONGER:
            closed = self._close_open_states(prototype, point, negated=False)
            if not closed:
                raise ValueError("NO_LONGER requires an existing open positive state")
            negative_opens = self._open_states(prototype, negated=True)
            if negative_opens:
                negated_ref = self._not_parent(negative_opens[-1])
            if negated_ref is None:
                _operand_ref, negated_ref = self._materialize_state(prototype, point, negated=True)
        elif operator is TransitionOperator.CONTINUE:
            opens = tuple(self._open_states(prototype, negated=False))
            if not opens:
                raise ValueError("CONTINUE requires an existing open positive state")
            state_ref = self.core.ref(opens[-1].uid)
        elif operator is TransitionOperator.AGAIN:
            if self._open_states(prototype, negated=False):
                raise ValueError("AGAIN requires the previous positive state to have ended")
            prior = []
            current_point = self._point_order_key(at_time_ref)
            assert current_point is not None
            for node in self._matching_states(prototype, negated=False):
                time_ref = node.actants.get(ActantRole.TIME)
                if not isinstance(time_ref, Ref):
                    continue
                value = temporal_value_from_ref(self.core, time_ref)
                if value is None or value.kind is not TemporalKind.INTERVAL or value.end is None:
                    continue
                end = _parse_bound(value.end)
                if end is not None and end[1] < current_point:
                    prior.append(node)
            if not prior:
                raise ValueError("AGAIN requires a previous completed positive state interval")
            # If an explicit negative interval exists (for example because STOP was
            # observed), restarting P ends that interval.  If no such interval was
            # stored, AGAIN does *not* invent one.
            self._close_open_states(prototype, point, negated=True)
            state_ref, _ = self._materialize_state(prototype, point, negated=False)
        else:  # pragma: no cover - Enum exhaustiveness
            raise AssertionError(operator)

        supports = tuple(ref for ref in (proposition_ref, at_time_ref, *closed) if ref is not None)
        for conclusion in (state_ref, negated_ref):
            if conclusion is not None:
                self.core.add_support(
                    conclusion,
                    SupportRecord(
                        premise_refs=supports,
                        rule_id=f"STATE_{operator.value}",
                    ),
                )
        return StateTransitionResult(
            transition_ref=transition_ref,
            state_ref=state_ref,
            negated_state_ref=negated_ref,
            closed_state_refs=closed,
        )
