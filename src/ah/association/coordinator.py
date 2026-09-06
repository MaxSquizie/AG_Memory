from __future__ import annotations

from dataclasses import dataclass

from ah.core import AHCore
from ah.ignition import IgnitionEngine, PropagationEvent
from ah.inference import GoalMode, GoalSpec
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import Domain, FunctionSymbol, Group, Hypernode, Ref, RefKind, Template

from .contracts import (
    AssociationBudget,
    AssociationDomainPolicy,
    AssociationGoal,
    AssociationHop,
    AssociationHopKind,
    AssociationOutcome,
    AssociationPath,
    AssociationStatus,
    AssociationTraceEvent,
    AssociationTraceKind,
)


_LEFT = "LEFT"
_RIGHT = "RIGHT"
_FRONTS = (_LEFT, _RIGHT)


@dataclass(frozen=True, slots=True)
class _Parent:
    parent_uid: str | None
    hop: AssociationHop | None


@dataclass(frozen=True, slots=True)
class _Pending:
    depth: int
    parent: _Parent


class AssociationSearchState:
    """Runtime-only ancestry/provenance for two excitation fronts.

    The state has no UID, is never persisted and never mutates canonical topology.
    It exists solely to distinguish genuine convergence from unrelated warm
    Workspace activity.
    """

    def __init__(self, goal: AssociationGoal) -> None:
        self.goal = goal
        self.parents: dict[str, dict[str, _Parent]] = {_LEFT: {}, _RIGHT: {}}
        self.depths: dict[str, dict[str, int]] = {_LEFT: {}, _RIGHT: {}}
        self.discovered_tick: dict[str, dict[str, int]] = {_LEFT: {}, _RIGHT: {}}
        self.pending: dict[str, dict[str, _Pending]] = {_LEFT: {}, _RIGHT: {}}
        self.trace: list[AssociationTraceEvent] = []
        self.scheduled_states = 0

        self._discover_root(_LEFT, goal.left)
        self._discover_root(_RIGHT, goal.right)

    def _discover_root(self, front: str, ref: Ref) -> None:
        self.parents[front][ref.uid] = _Parent(None, None)
        self.depths[front][ref.uid] = 0
        self.discovered_tick[front][ref.uid] = -1
        self.scheduled_states += 1

    def has(self, front: str, uid: str) -> bool:
        return uid in self.parents[front]

    def is_pending(self, front: str, uid: str) -> bool:
        return uid in self.pending[front]

    def depth(self, front: str, uid: str) -> int:
        return self.depths[front][uid]

    def schedule(self, front: str, target: Ref, *, depth: int, parent: _Parent) -> bool:
        if self.has(front, target.uid):
            return False
        previous = self.pending[front].get(target.uid)
        if previous is not None:
            # Keep the shallowest path; tie-break deterministically by the
            # diagnostic relation/via UID so results do not depend on traversal order.
            old_key = (
                previous.depth,
                previous.parent.hop.relation if previous.parent.hop else "",
                previous.parent.hop.via_uid or "" if previous.parent.hop else "",
                previous.parent.parent_uid or "",
            )
            new_key = (
                depth,
                parent.hop.relation if parent.hop else "",
                parent.hop.via_uid or "" if parent.hop else "",
                parent.parent_uid or "",
            )
            if new_key >= old_key:
                return False
            self.pending[front][target.uid] = _Pending(depth, parent)
            return False
        self.pending[front][target.uid] = _Pending(depth, parent)
        self.scheduled_states += 1
        return True

    def activate(self, front: str, ref: Ref, *, tick: int) -> bool:
        if self.has(front, ref.uid):
            return False
        pending = self.pending[front].pop(ref.uid, None)
        if pending is None:
            return False
        self.parents[front][ref.uid] = pending.parent
        self.depths[front][ref.uid] = pending.depth
        self.discovered_tick[front][ref.uid] = tick
        return True

    def intersection(self) -> set[str]:
        return set(self.parents[_LEFT]) & set(self.parents[_RIGHT])

    def path(self, front: str, common: Ref, core: AHCore) -> AssociationPath:
        origin = self.goal.left if front == _LEFT else self.goal.right
        refs_rev: list[Ref] = [common]
        hops_rev: list[AssociationHop] = []
        uid = common.uid
        while uid != origin.uid:
            parent = self.parents[front].get(uid)
            if parent is None or parent.parent_uid is None or parent.hop is None:
                raise RuntimeError(f"Broken association ancestry for {front}:{uid}")
            hops_rev.append(parent.hop)
            uid = parent.parent_uid
            refs_rev.append(core.ref(uid))
        refs = tuple(reversed(refs_rev))
        hops = tuple(reversed(hops_rev))
        return AssociationPath(origin=origin, common=common, refs=refs, hops=hops)


class AssociationCoordinator:
    """Goal-driven two-front associative search over ordinary AH activation.

    Association is deliberately separate from InferenceEngine. Search seeds both
    concepts, lets the normal synchronous Ignition engine propagate packets, and
    keeps only runtime ancestry for the two fronts. Goal-generated narrow reverse
    queries expose canonical incidence that the directed activation packet flow does
    not traverse by itself (actant->N, operand->g, member->k, incoming L, etc.).

    A convergence is *not* a proof and no conclusion/support is materialized.
    """

    def __init__(self, core: AHCore, ignition: IgnitionEngine) -> None:
        if ignition.core is not core:
            raise ValueError("AssociationCoordinator core and ignition must share one AHCore")
        self.core = core
        self.ignition = ignition

    def solve(
        self,
        request: AssociationGoal | GoalSpec,
        *,
        budget: AssociationBudget | None = None,
        domain_policy: AssociationDomainPolicy = AssociationDomainPolicy.ALL,
    ) -> AssociationOutcome:
        goal = self._normalize_goal(request)
        budget = budget or AssociationBudget()
        self._validate_goal(goal, domain_policy)
        state = AssociationSearchState(goal)
        start_tick = self.ignition.tick_index
        state.trace.append(
            AssociationTraceEvent(
                AssociationTraceKind.GOAL_START,
                tick=start_tick,
                detail=(
                    f"FIND_ASSOCIATIVE_CONNECTION({goal.left.uid},{goal.right.uid}); "
                    f"domain_policy={domain_policy.value}"
                ),
            )
        )

        if goal.left == goal.right:
            common = goal.left
            state.trace.append(
                AssociationTraceEvent(
                    AssociationTraceKind.CONVERGENCE,
                    tick=start_tick,
                    ref=common,
                    detail="identical association origins",
                )
            )
            state.trace.append(
                AssociationTraceEvent(
                    AssociationTraceKind.GOAL_STOP,
                    tick=start_tick,
                    ref=common,
                    detail=AssociationStatus.FOUND.value,
                )
            )
            return self._outcome(
                state, AssociationStatus.FOUND, common, start_tick, domain_policy
            )

        # Strong query seeds are attention, not factual confirmation. Warm Workspace
        # is left intact; only ancestry descended from these two fresh seeds counts.
        self._seed(goal.left, _LEFT, state, tick=start_tick)
        self._seed(goal.right, _RIGHT, state, tick=start_tick)

        budget_hit = False
        depth_hit = False
        ticks_executed = 0

        for _ in range(budget.max_ticks):
            result = self.ignition.tick(include_pacemaker=False)
            ticks_executed += 1
            tick = result.tick

            newly_activated: dict[str, list[Ref]] = {_LEFT: [], _RIGHT: []}
            activation_by_uid = {ref.uid: ref for ref in result.activation_events}

            # Roots are already ancestry-known, but their first real query seed still
            # receives an ACTIVATION event and should initiate reverse/incidence queries.
            for front, root in ((_LEFT, goal.left), (_RIGHT, goal.right)):
                if root.uid in activation_by_uid:
                    newly_activated[front].append(root)
                    state.trace.append(
                        AssociationTraceEvent(
                            AssociationTraceKind.ACTIVATION,
                            tick=tick,
                            front=front,
                            ref=root,
                            detail="association origin activation",
                        )
                    )

            for ref in result.activation_events:
                for front in _FRONTS:
                    if state.activate(front, ref, tick=tick):
                        newly_activated[front].append(ref)
                        state.trace.append(
                            AssociationTraceEvent(
                                AssociationTraceKind.ACTIVATION,
                                tick=tick,
                                front=front,
                                ref=ref,
                                detail=f"depth={state.depth(front, ref.uid)}",
                            )
                        )

            common = self._select_common(state)
            if common is not None:
                state.trace.append(
                    AssociationTraceEvent(
                        AssociationTraceKind.CONVERGENCE,
                        tick=tick,
                        ref=common,
                        detail=(
                            f"left_depth={state.depth(_LEFT, common.uid)}; "
                            f"right_depth={state.depth(_RIGHT, common.uid)}"
                        ),
                    )
                )
                state.trace.append(
                    AssociationTraceEvent(
                        AssociationTraceKind.GOAL_STOP,
                        tick=tick,
                        ref=common,
                        detail=AssociationStatus.FOUND.value,
                    )
                )
                return self._outcome(
                    state, AssociationStatus.FOUND, common, start_tick, domain_policy,
                    ticks_executed=ticks_executed,
                )

            # Record ordinary Ignition propagation as ancestry that may activate on
            # the next synchronous tick. One packet still crosses <=1 edge per tick.
            for event in result.propagations:
                for front in _FRONTS:
                    if not state.has(front, event.source.uid):
                        continue
                    source_depth = state.depth(front, event.source.uid)
                    next_depth = source_depth + 1
                    if next_depth > budget.max_depth:
                        depth_hit = True
                        continue
                    if not self._allowed(event.target, domain_policy):
                        continue
                    if state.scheduled_states >= budget.max_expanded_states:
                        budget_hit = True
                        continue
                    hop = AssociationHop(
                        source=event.source,
                        target=event.target,
                        kind=AssociationHopKind.PROPAGATION,
                        relation=event.relation,
                        tick=tick,
                        via_uid=event.via_uid,
                    )
                    state.schedule(
                        front,
                        event.target,
                        depth=next_depth,
                        parent=_Parent(event.source.uid, hop),
                    )

            # GoalSpec may issue narrow queries from the *newly activated* focus.
            # Those candidates receive ordinary QUERY_RECALL seeds and must actually
            # activate on a subsequent Ignition tick before joining the front.
            for front in _FRONTS:
                for ref in sorted(newly_activated[front], key=lambda item: item.uid):
                    source_depth = state.depth(front, ref.uid)
                    if source_depth >= budget.max_depth:
                        depth_hit = True
                        continue
                    query_neighbors = self._query_neighbors(ref, domain_policy)
                    state.trace.append(
                        AssociationTraceEvent(
                            AssociationTraceKind.MEMORY_QUERY,
                            tick=tick,
                            front=front,
                            ref=ref,
                            source=ref,
                            query_kind="ACTIVE_INCIDENCE",
                            candidate_count=len(query_neighbors),
                            detail="goal-derived narrow reverse/incidence query",
                        )
                    )
                    for target, relation, via_uid in query_neighbors:
                        if state.has(front, target.uid) or state.is_pending(front, target.uid):
                            continue
                        if state.scheduled_states >= budget.max_expanded_states:
                            budget_hit = True
                            break
                        hop = AssociationHop(
                            source=ref,
                            target=target,
                            kind=AssociationHopKind.MEMORY_QUERY,
                            relation=relation,
                            tick=tick,
                            via_uid=via_uid,
                        )
                        scheduled = state.schedule(
                            front,
                            target,
                            depth=source_depth + 1,
                            parent=_Parent(ref.uid, hop),
                        )
                        if scheduled:
                            self._seed(target, front, state, tick=tick, query_generated=True)

            if budget_hit:
                # Stop immediately instead of walking extra graph after the resource
                # contract has been reached. Already scheduled Ignition packets stay
                # ordinary runtime state; no canonical search state exists to clean up.
                state.trace.append(
                    AssociationTraceEvent(
                        AssociationTraceKind.GOAL_STOP,
                        tick=tick,
                        detail=AssociationStatus.BUDGET_EXHAUSTED.value,
                    )
                )
                return self._outcome(
                    state, AssociationStatus.BUDGET_EXHAUSTED, None, start_tick,
                    domain_policy, ticks_executed=ticks_executed,
                )

            # If neither front has any not-yet-activated ancestry and Ignition
            # scheduled no new packet, the search is exhausted before max_ticks.
            if not state.pending[_LEFT] and not state.pending[_RIGHT] and not result.propagations:
                status = AssociationStatus.DEPTH_EXHAUSTED if depth_hit else AssociationStatus.NOT_FOUND
                state.trace.append(
                    AssociationTraceEvent(
                        AssociationTraceKind.GOAL_STOP,
                        tick=tick,
                        detail=status.value,
                    )
                )
                return self._outcome(
                    state, status, None, start_tick, domain_policy,
                    ticks_executed=ticks_executed,
                )

        tick = self.ignition.tick_index
        state.trace.append(
            AssociationTraceEvent(
                AssociationTraceKind.GOAL_STOP,
                tick=tick,
                detail=AssociationStatus.RESOURCE_LIMIT.value,
            )
        )
        return self._outcome(
            state, AssociationStatus.RESOURCE_LIMIT, None, start_tick, domain_policy,
            ticks_executed=ticks_executed,
        )

    @staticmethod
    def _normalize_goal(request: AssociationGoal | GoalSpec) -> AssociationGoal:
        if isinstance(request, AssociationGoal):
            return request
        if request.mode is not GoalMode.ASSOCIATION:
            raise ValueError("AssociationCoordinator requires GoalSpec.mode=ASSOCIATION")
        if not isinstance(request.target, AssociationGoal):
            raise TypeError("Association GoalSpec target must be AssociationGoal")
        return request.target

    def _validate_goal(
        self, goal: AssociationGoal, domain_policy: AssociationDomainPolicy
    ) -> None:
        for ref in (goal.left, goal.right):
            if not self.core.store.has_uid(ref.uid):
                raise KeyError(ref.uid)
            if self.core.store.kind_of(ref.uid) is not ref.kind:
                raise TypeError(f"Reference kind mismatch for {ref.uid}")
            if not self._allowed(ref, domain_policy):
                raise ValueError(
                    f"Association origin {ref.uid} is excluded by {domain_policy.value}"
                )

    def _allowed(self, ref: Ref, policy: AssociationDomainPolicy) -> bool:
        if ref.kind is RefKind.L:
            return False
        if policy is AssociationDomainPolicy.ALL:
            return True
        domain = self.core.store.domain_of(ref.uid)
        return domain is not Domain.H

    def _seed(
        self,
        ref: Ref,
        front: str,
        state: AssociationSearchState,
        *,
        tick: int,
        query_generated: bool = False,
    ) -> None:
        self.ignition.apply_seed_requests(
            (ActivationSeedRequest(ref, SeedReason.QUERY_RECALL),)
        )
        state.trace.append(
            AssociationTraceEvent(
                AssociationTraceKind.SEED,
                tick=tick,
                front=front,
                ref=ref,
                detail=("goal-generated query seed" if query_generated else "association origin seed"),
            )
        )

    def _query_neighbors(
        self, ref: Ref, policy: AssociationDomainPolicy
    ) -> tuple[tuple[Ref, str, str | None], ...]:
        """Narrow canonical incidence queries derived only from current focus.

        The normal Ignition engine already follows outgoing L, S->T, T->N and
        N->actants. Here we expose the reverse/compositional directions required to
        *expand a representation* without granting arbitrary global reads.
        """
        candidates: dict[str, tuple[Ref, str, str | None]] = {}

        def add(target: Ref, relation: str, via_uid: str | None = None) -> None:
            if target.uid == ref.uid or not self._allowed(target, policy):
                return
            candidates.setdefault(target.uid, (target, relation, via_uid))

        # Reverse hyperedge incidence: any current canonical ref may be an N actant.
        for node in self.core.store.hypernodes_for_actant(ref.uid):
            if node.weight <= 0:
                continue
            add(self.core.ref(node.uid), "ACTANT_OF", node.uid)

        # Reverse functional/group incidence.
        for parent in self.core.store.function_parents(ref.uid):
            add(self.core.ref(parent.uid), "OPERAND_OF", parent.uid)
        for group in self.core.store.groups_containing(ref.uid):
            add(self.core.ref(group.uid), "MEMBER_OF", group.uid)

        # Activation may travel opposite to a directed semantic L without asserting
        # the reverse logical relation.
        for link in self.core.store.incoming_links(ref.uid):
            if link.weight <= 0:
                continue
            add(link.source, f"L_BACKWARD:{link.relation_id}", link.uid)

        obj = self.core.store.get_element_any_domain(ref.uid) if ref.kind not in {RefKind.S, RefKind.L} else None
        if isinstance(obj, Hypernode):
            add(obj.template, "N_TEMPLATE", obj.uid)
        elif isinstance(obj, Template):
            add(obj.predicate, "T_PREDICATE", obj.uid)
        elif isinstance(obj, FunctionSymbol):
            for operand in obj.operands:
                if isinstance(operand, Ref):
                    add(operand, f"G_OPERAND:{obj.function_id}", obj.uid)
        elif isinstance(obj, Group):
            for member in obj.members:
                add(member, "K_MEMBER", obj.uid)

        return tuple(candidates[uid] for uid in sorted(candidates))

    def _select_common(self, state: AssociationSearchState) -> Ref | None:
        common = state.intersection()
        if not common:
            return None
        # No semantic hub filter. Deterministic selection only chooses which valid
        # convergence to report first; every discovered common node remains exposed.
        def key(uid: str) -> tuple[int, int, int, str]:
            left_tick = state.discovered_tick[_LEFT].get(uid, -1)
            right_tick = state.discovered_tick[_RIGHT].get(uid, -1)
            convergence_tick = max(left_tick, right_tick)
            left_depth = state.depths[_LEFT][uid]
            right_depth = state.depths[_RIGHT][uid]
            return (convergence_tick, left_depth + right_depth, max(left_depth, right_depth), uid)

        return self.core.ref(min(common, key=key))

    def _outcome(
        self,
        state: AssociationSearchState,
        status: AssociationStatus,
        common: Ref | None,
        start_tick: int,
        policy: AssociationDomainPolicy,
        *,
        ticks_executed: int = 0,
    ) -> AssociationOutcome:
        common_refs = tuple(
            self.core.ref(uid)
            for uid in sorted(
                state.intersection(),
                key=lambda uid: (
                    max(
                        state.discovered_tick[_LEFT].get(uid, -1),
                        state.discovered_tick[_RIGHT].get(uid, -1),
                    ),
                    state.depths[_LEFT][uid] + state.depths[_RIGHT][uid],
                    uid,
                ),
            )
        )
        left_path = state.path(_LEFT, common, self.core) if common is not None else None
        right_path = state.path(_RIGHT, common, self.core) if common is not None else None
        left_activated = tuple(
            self.core.ref(uid)
            for uid in sorted(state.parents[_LEFT], key=lambda uid: (state.depths[_LEFT][uid], uid))
        )
        right_activated = tuple(
            self.core.ref(uid)
            for uid in sorted(state.parents[_RIGHT], key=lambda uid: (state.depths[_RIGHT][uid], uid))
        )
        return AssociationOutcome(
            status=status,
            goal=state.goal,
            common_ref=common,
            left_path=left_path,
            right_path=right_path,
            common_candidates=common_refs,
            left_activated=left_activated,
            right_activated=right_activated,
            expanded_states=len(state.parents[_LEFT]) + len(state.parents[_RIGHT]),
            ticks_executed=ticks_executed,
            trace=tuple(state.trace),
            domain_policy=policy,
        )
