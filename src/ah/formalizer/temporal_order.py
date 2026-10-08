"""Guaranteed ordering of closed temporal anchors; no event-time guessing."""
from ah.model import TimeLiteral


def compare_regions(operator,first,second):
    """All-realization ordering; unknown event time is never an interval fact."""
    from .temporal_license import covers
    if operator=='AFTER': return compare_regions('BEFORE',second,first)
    def bounds(r): return (r.point,r.point) if r.kind=='POINT' else (r.lo,r.hi)
    alo,ahi=bounds(first); blo,bhi=bounds(second)
    if None in (alo,ahi,blo,bhi): return None
    if operator=='BEFORE':
        if ahi<blo: return True
        if alo>=bhi: return False
        return None
    if operator=='DURING':
        if second.kind in {'CONTINUOUS','POINT'} and covers(second,first) is True: return True
        if ahi<blo or bhi<alo: return False
        return None
    raise ValueError('REGISTRY_REJECT')


def prove_order(core,ledger,pattern,goal,budget,workspace):
    """Only live concrete evidence licenses inferred ordering of events."""
    from .native_queries import Pattern,_matching_refs,_answers_window
    from ah.inference.contracts import NativeFormulaGoal
    from .temporal_license import TemporalRegion,normalize
    from .canonical_ledger import region
    from itertools import product
    if len(pattern.members)!=2: raise ValueError('REGISTRY_REJECT')
    options=[]
    for operand in pattern.members:
        if isinstance(operand,TimeLiteral):
            lo,hi=operand.bounds[0],operand.bounds[-1]
            options.append([(TemporalRegion('POINT',point=lo) if lo==hi else TemporalRegion('CONTINUOUS',lo=lo,hi=hi),())]); continue
        if not isinstance(operand,Pattern): return None
        scope=goal
        if operand.temporal:
            own=normalize(region(operand.temporal))
            scope=NativeFormulaGoal(operand,own.point if own.kind=='POINT' else None,
                (own.lo,own.hi) if own.kind in {'CONTINUOUS','EXISTENTIAL'} else None)
        refs=_matching_refs(core,ledger,operand,limit=min(4096,max(1,budget[0])),workspace=workspace)
        candidates=[]
        for uid in refs:
            for aid,a in ledger.data['assertions'].items():
                budget[0]-=1
                if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
                if a['target_ref']==uid and ledger.evidence_live({'record_id':aid}):
                    temporal=normalize(region(a['region']))
                    if not _answers_window(temporal,scope): continue
                    candidates.append((temporal,(core.ref(uid),)))
                    if len(candidates)>64: raise ValueError('COMPUTATION_LIMIT')
        options.append(candidates)
    known=[]
    for i,(a,b) in enumerate(product(*options)):
        budget[0]-=1
        if i>=256 or budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
        result=compare_regions(pattern.operator,a[0],b[0])
        if result is not None: known.append((result,tuple(dict.fromkeys((*a[1],*b[1])))))
    # A concrete proved pair witnesses the existential event query. A failed
    # pair does not refute other occurrences in an open domain; only an
    # explicit negative ordering statement can provide that refutation.
    return next((item for item in known if item[0]),None)


def compare_anchors(operator,first:TimeLiteral,second:TimeLiteral):
    alo,ahi=first.bounds[0],first.bounds[-1]
    blo,bhi=second.bounds[0],second.bounds[-1]
    if operator=='AFTER':
        return compare_anchors('BEFORE',second,first)
    if operator=='BEFORE':
        if ahi<blo: return True
        if alo>=bhi: return False
        return None
    if operator=='DURING':
        return blo<=alo and ahi<=bhi
    raise ValueError('REGISTRY_REJECT')
