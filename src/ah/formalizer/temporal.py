"""Explicit temporal assertions; an observation at t never implies [t,infinity)."""
from dataclasses import dataclass
from .temporal_license import TemporalRegion,normalize,covers,point,cont

@dataclass(frozen=True)
class TimeAssertion:
    assertion_id: str
    valid_from: int
    valid_until: int | None=None
    tags: frozenset[str]=frozenset()
    kind: str='POINT'
    status: str='LIVE'

    def covers(self,t):
        if self.status!='LIVE': return False
        if self.kind=='POINT': return t==self.valid_from
        if self.kind=='CONTINUOUS': return self.valid_until is not None and self.valid_from<=t<=self.valid_until
        return self.kind=='EXISTENTIAL' and self.valid_until==self.valid_from==t

class TemporalLedger:
    def __init__(self,store=None): self._store=store; self._intervals={}
    def assert_true(self,assertion_id,at,tags=frozenset(),*,until=None,interval_semantics=None):
        if self._store is not None: raise ValueError('use atomic ADD_TIME_ASSERTION with its support/provenance')
        kind='POINT' if until is None else interval_semantics or 'EXISTENTIAL'
        if kind not in {'POINT','CONTINUOUS','EXISTENTIAL'} or (until is not None and until<at): raise ValueError('TIME_ASSERTION_INVALID')
        ta=TimeAssertion(assertion_id,at,until,frozenset(tags),kind)
        self._intervals.setdefault(assertion_id,[]).append(ta); return ta
    def close(self,assertion_id,at):
        raise ValueError('interval boundaries are immutable; use per-assertion retraction')
    def is_true_at(self,assertion_id,t): return any(a.covers(t) for a in self._intervals.get(assertion_id,()))
    def state_at(self,t): return {uid for uid in self._intervals if self.is_true_at(uid,t)}
    def intervals(self,assertion_id): return tuple(self._intervals.get(assertion_id,()))

def assert_true_at(ledger,facts):
    for uid,t in facts: ledger.assert_true(uid,t)
