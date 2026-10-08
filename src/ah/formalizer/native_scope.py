"""Read-only, path-sensitive hypothetical views over canonical V7 records.

A view shares canonical node/record identities. Suppression is a runtime mask;
it never retracts records, adds assumptions to AH or writes a goal decision.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Mapping

from ah.inference.context import ProofContext
from ah.inference.contracts import NativeFormulaGoal, LogicalStatus, FormulaQueryConclusion
from ah.model import BoundVar

from .canonical_ledger import CanonicalLedger, region, simultaneous
from .temporal_license import TemporalRegion, normalize, covers


@dataclass(frozen=True)
class Assumption:
    pattern: object
    positive: bool
    temporal: TemporalRegion


@dataclass(slots=True)
class NativeProofContext(ProofContext):
    overrides: tuple[Assumption, ...] = ()

    def is_counterfactual(self):
        return True


def overrides(context):
    inherited = overrides(context.parent) if context is not None and context.parent is not None else ()
    return (*inherited, *getattr(context, 'overrides', ()))


def content_signature(pattern):
    from .native_queries import Pattern
    from .query_bindings import pattern_signature
    def strip(p):
        if not isinstance(p, Pattern):
            return p
        return replace(p, temporal=None, members=tuple(strip(x) for x in p.members),
                       actants=tuple((r, strip(v)) for r, v in p.actants))
    return pattern_signature(strip(pattern))


def _possible_overlap(a, b):
    a, b = normalize(a), normalize(b)
    if 'UNDATED' in {a.kind, b.kind}:
        return True
    def bounds(r):
        return (r.point, r.point) if r.kind == 'POINT' else (r.lo, r.hi)
    lo, hi = bounds(a); other_lo, other_hi = bounds(b)
    return (None in (lo, hi, other_lo, other_hi)
            or max(lo, other_lo) <= min(hi, other_hi))


def query_region(goal):
    if getattr(goal, 'temporal_point', None) is not None:
        return TemporalRegion('POINT', point=goal.temporal_point)
    if getattr(goal, 'temporal_window', None) is not None:
        return TemporalRegion('CONTINUOUS', lo=goal.temporal_window[0], hi=goal.temporal_window[1])
    return TemporalRegion('UNDATED')


def make_context(context, assumptions):
    from .native_queries import Pattern, QueryVar
    flattened = []
    def closed(p, bound=frozenset()):
        if isinstance(p, QueryVar):
            return False
        if isinstance(p, BoundVar):
            return p.local_id in bound
        if not isinstance(p, Pattern):
            return True
        inner = bound
        if p.operator in {'FORALL','EXISTS','AT_LEAST_N','EXACTLY_N','AT_MOST_N'}:
            if not p.members or not isinstance(p.members[0], BoundVar):
                return False
            inner = bound | {p.members[0].local_id}
        return all(closed(x, inner) for x in p.members) and all(closed(v, inner) for r, v in p.actants)
    def collect(p, inherited=None):
        if not isinstance(p, Pattern) or not closed(p):
            raise ValueError('COUNTERFACTUAL_ASSUMPTION_INVALID')
        temporal = normalize(region(p.temporal)) if p.temporal is not None else inherited or TemporalRegion('UNDATED')
        flattened.append(Assumption(p, True, temporal))
        if p.operator == 'AND':
            for child in p.members:
                collect(child, temporal)
        elif p.operator == 'NOT':
            if len(p.members) != 1 or not isinstance(p.members[0], Pattern):
                raise ValueError('COUNTERFACTUAL_ASSUMPTION_INVALID')
            child = p.members[0]
            child_region = normalize(region(child.temporal)) if child.temporal is not None else temporal
            flattened.append(Assumption(child, False, child_region))
    for p in assumptions:
        collect(p)
    if len(flattened) > 128:
        raise ValueError('COMPUTATION_LIMIT')
    for i, a in enumerate(flattened):
        for b in flattened[:i]:
            if (a.positive != b.positive and content_signature(a.pattern) == content_signature(b.pattern)
                    and simultaneous(a.temporal, b.temporal)):
                raise ValueError('COUNTERFACTUAL_ASSUMPTIONS_CONFLICT')
    return NativeProofContext(parent=context, bindings=context.bindings.child(), overrides=tuple(flattened))


def assumed_status(pattern, goal, context):
    from .native_queries import _answers_window
    key = content_signature(pattern)
    wanted = query_region(goal)
    for assumption in reversed(overrides(context)):
        if content_signature(assumption.pattern) != key:
            continue
        if wanted.kind != 'UNDATED' and not _possible_overlap(wanted, assumption.temporal):
            continue
        if wanted.kind == 'UNDATED':
            licensed = True
        elif assumption.positive:
            licensed = _answers_window(assumption.temporal, goal)
        else:
            licensed = covers(assumption.temporal, wanted) is True
        if not licensed:
            return LogicalStatus.UNKNOWN, ()
        return (LogicalStatus.PROVED if assumption.positive else LogicalStatus.DISPROVED), (assumption.temporal,)
    return None


class ProofLedger(CanonicalLedger):
    """Replaceable read projection. A masked assertion invalidates its own paths."""
    def __init__(self, base, blocked_supports, blocked_assertions):
        self.data = dict(base.data)
        self.data['supports'] = MaskedRecords(base.data['supports'],blocked_supports)
        self.data['assertions'] = MaskedRecords(base.data['assertions'],blocked_assertions)

    def _write_forbidden(self, *args, **kwargs):
        raise ValueError('COUNTERFACTUAL_WRITE_FORBIDDEN')

    add_support = add_assertion = retract = supersede = refresh = _write_forbidden


class MaskedRecords(Mapping):
    def __init__(self,records,blocked):
        self.records,self.blocked=records,frozenset(blocked)

    def __getitem__(self,key):
        record=self.records[key]
        return {**record,'status':'SUPPRESSED'} if key in self.blocked else record

    def __iter__(self): return iter(self.records)
    def __len__(self): return len(self.records)


def proof_ledger(core, base, context, goal, budget, workspace=()):
    from .native_queries import Pattern, _matching_refs
    assumptions = overrides(context)
    if not assumptions:
        return base
    blocked_supports, blocked_assertions = set(), set()
    active = query_region(goal)
    by_node = {}
    for assumption in assumptions:
        if not _possible_overlap(assumption.temporal, active):
            continue
        opposite = Pattern('NOT', (assumption.pattern,)) if assumption.positive else assumption.pattern
        targets = _matching_refs(core, base, opposite, limit=min(4096, max(1, budget[0])), workspace=workspace)
        # An asserted conjunction entails its conjuncts. Mask its conflicting
        # proof too, otherwise a direct AND lookup could bypass the hypothesis
        # even after the concrete conjunct's derived support was suppressed.
        queue=list(targets); visited=set(targets)
        for uid in queue:
            for parent in core.store.function_parents(uid):
                budget[0]-=1
                if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
                if parent.function_id=='AND' and parent.uid not in visited:
                    visited.add(parent.uid); queue.append(parent.uid)
        targets=queue
        for uid in targets:
            by_node.setdefault(uid, []).append(assumption.temporal)
    from .native_records import record_index
    index=record_index(core,base)
    for uid,assumption_regions in by_node.items():
        for sid in index['supports'].get(uid,()):
            budget[0]-=1
            if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
            dated=index['assertions'].get(sid,())
            for aid in dated:
                a=base.data['assertions'][aid]
                budget[0]-=1
                if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
                if (_possible_overlap(region(a['region']),active)
                        and any(_possible_overlap(region(a['region']),r) for r in assumption_regions)):
                    blocked_assertions.add(aid)
            if not dated or all(aid in blocked_assertions or base.data['assertions'][aid]['status']!='LIVE' for aid in dated):
                blocked_supports.add(sid)
    # Canonical fixed-point liveness also filters binding dependencies and every
    # derived support that names a suppressed premise/assertion. Independent
    # supports of the same conclusion remain available.
    return ProofLedger(base, blocked_supports, blocked_assertions)


def solve_counterfactual(engine, goal, query, workspace, attention, context, runtime, budget, depth, outcome):
    from .native_queries import solve_native_goal,Pattern,QueryVar
    from .native_derivations import pattern_from_ref
    from ah.inference.contracts import ExistsGoal,RoleFillGoal,MultiRoleFillGoal,NativeBindingGoal,ExistingRefConclusion,CountGoal
    from ah.model import Ref
    assumptions=tuple(pattern_from_ref(engine.core,engine.core._formalizer_adapter.ledger,a.uid,budget) if isinstance(a,Ref) else a for a in goal.assumptions)
    scoped = make_context(context, assumptions)
    target=goal.target
    if isinstance(target,(ExistsGoal,RoleFillGoal,MultiRoleFillGoal)):
        roles=(target.requested_role,) if isinstance(target,RoleFillGoal) else target.requested_roles if isinstance(target,MultiRoleFillGoal) else ()
        pattern=Pattern(template_ref=target.template_ref.uid,
                        actants=tuple(target.known_roles.items())+tuple((r,QueryVar(r.value)) for r in roles))
        target=(NativeBindingGoal(pattern,tuple(r.value for r in roles),'WH',target.temporal_point,target.temporal_window) if roles else
                NativeFormulaGoal(pattern,target.temporal_point,target.temporal_window))
    if not hasattr(target,'pattern') and not isinstance(target,CountGoal):
        raise ValueError('COUNTERFACTUAL_TARGET_UNBOUND')
    child = solve_native_goal(engine, target, query, workspace, attention, scoped, runtime,
                              _budget=budget, _depth=depth+1)
    conclusion=FormulaQueryConclusion('COUNTERFACTUAL', child.premise_refs) if child.conclusion is None or isinstance(child.conclusion,(FormulaQueryConclusion,ExistingRefConclusion)) else child.conclusion
    return replace(child, conclusion=conclusion,
                   proof_context=scoped, diagnostics=tuple(dict.fromkeys((*child.diagnostics, 'COUNTERFACTUAL_RUNTIME_ONLY'))))
