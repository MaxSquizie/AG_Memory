"""Window aggregates with explicit entity/event domains and identity evidence.

Snapshot cardinalities are not window cardinalities. Several observations or
supports of an occurrence are not automatically several real-world events.
"""
from __future__ import annotations

from dataclasses import replace
from ah.inference.contracts import NativeFormulaGoal, LogicalStatus, CountConclusion
from ah.model import RefKind


def solve_aggregate(engine,adapter,ledger,goal,query,workspace,attention,context,runtime,budget,depth,outcome):
    from .native_queries import Pattern,solve_native_goal,_matching_refs
    from .query_bindings import candidate_values,substitute,pattern_signature
    from .native_questions import _owner
    release=getattr(adapter,'resource_release',None)
    signature=pattern_signature(goal.pattern)
    certs=[]
    paths=ledger.paths()
    if release is not None and release.sha256==goal.resource_snapshot and not context.is_counterfactual() and not goal.source_scope:
        release.assert_integrity()
        certs=[c for c in release.resources.get('CountDomain',{}).get('entries',())
               if c['pattern_signature']==signature and c['count_unit']==goal.count_unit
               and c.get('count_variable')==goal.count_variable and tuple(c['request_window'])==tuple(goal.temporal_window)
               and (goal.domain_certificate is None or c['domain_id']==goal.domain_certificate)
               and all(s in paths for s in c['completeness_evidence'])]
    def prove(pattern):
        answer=solve_native_goal(engine,NativeFormulaGoal(pattern,None,goal.temporal_window,goal.workspace_refs,goal.source_scope),
                                 query,workspace,attention,context,runtime,_budget=budget,_depth=depth+1)
        if 'COMPUTATION_LIMIT' in answer.diagnostics:
            raise ValueError('COMPUTATION_LIMIT')
        return answer
    witnessed={}; proof_refs=[]; unknown=False
    if goal.count_unit=='ENTITY':
        values=candidate_values(engine.core,ledger,goal.pattern,(goal.count_variable,),budget,context=context)[goal.count_variable]
        for uid in sorted(values):
            entity=engine.core.ref(uid)
            if entity.kind is not RefKind.M: continue
            answer=prove(substitute(goal.pattern,{goal.count_variable:entity}))
            if answer.status is LogicalStatus.UNKNOWN: unknown=True
            if answer.status is LogicalStatus.PROVED:
                witnessed[uid]=set(r.uid for r in answer.premise_refs if r.kind in {RefKind.N,RefKind.G})
                proof_refs.extend(answer.premise_refs)
        lower=len(witnessed)
    else:
        owner=_owner(goal.pattern)
        if owner.operator is not None or owner.lexical_anchor:
            raise ValueError('COUNT_EVENT_OWNER_UNBOUND')
        nodes=_matching_refs(engine.core,ledger,owner,limit=min(4096,max(1,budget[0])),workspace=(*workspace,*goal.workspace_refs))
        def pin(p,uid):
            if p is owner: return replace(p,occurrence_ref=uid)
            if not isinstance(p,Pattern): return p
            return replace(p,members=tuple(pin(x,uid) for x in p.members),actants=tuple((r,pin(v,uid)) for r,v in p.actants))
        for uid in nodes:
            if ledger.data['nodes'].get(uid,{}).get('temporal_mode')!='EVENT': continue
            if ledger.query(uid,window=goal.temporal_window)['answer']!='YES': continue
            answer=prove(pin(goal.pattern,uid))
            if answer.status is LogicalStatus.UNKNOWN: unknown=True
            if answer.status is LogicalStatus.PROVED:
                witnessed[uid]={uid}; proof_refs.extend(answer.premise_refs)
        # Without a grounded grouping/distinctness declaration, two records
        # can describe the same real event. Only existence gives a sound lower
        # bound; canonical occurrence-local UIDs alone do not prove distinctness.
        lower=1 if witnessed else 0
    complete=False; diagnostics=[]; chosen_members=None; completeness_refs=[]
    for cert in sorted(certs,key=lambda c:c['domain_id']):
        if goal.count_unit=='EVENT' and not all(s in paths for s in cert.get('identity_evidence',())):
            continue
        members=cert['members']; matched={}; coverage=set(); valid=True
        for member in members:
            if goal.count_unit=='ENTITY':
                entity=member['entity_ref']
                node_refs=witnessed.get(entity,set())
                # A released member must still be a live proof of this exact
                # query and window, not merely a compatible entity name.
                if not set(member['node_refs'])&node_refs:
                    valid=False; break
                matched[member['key']]=entity
                coverage.add(entity)
            else:
                represented=set(member['node_refs'])&set(witnessed)
                if not represented:
                    valid=False; break
                matched[member['key']]=represented
                coverage.update(represented)
        if not valid:
            diagnostics.append('COUNT_DOMAIN_STALE'); continue
        if goal.count_unit=='EVENT':
            lower=max(lower,len(matched))
        if coverage!=set(witnessed) or unknown:
            diagnostics.append('COUNT_DOMAIN_STALE'); continue
        complete=True; chosen_members=matched
        completeness_refs=[engine.core.ref(ledger.data['supports'][s]['conclusion_ref'])
                           for s in (*cert['completeness_evidence'],*cert.get('identity_evidence',()))]
        break
    exact=len(chosen_members) if complete else None
    status=LogicalStatus.UNKNOWN; threshold=goal.expected_count
    if complete:
        truth=threshold is None or (exact==threshold if goal.comparison=='EXACTLY_N' else exact>=threshold if goal.comparison=='AT_LEAST_N' else exact<=threshold)
        status=LogicalStatus.PROVED if truth else LogicalStatus.DISPROVED
    elif threshold is not None:
        if goal.comparison=='AT_LEAST_N' and lower>=threshold: status=LogicalStatus.PROVED
        elif goal.comparison in {'EXACTLY_N','AT_MOST_N'} and lower>threshold: status=LogicalStatus.DISPROVED
    proofs=tuple(dict.fromkeys((*proof_refs,*completeness_refs)))
    if not complete:
        diagnostics.append('INCOMPLETE_COUNT_DOMAIN')
        if goal.count_unit=='EVENT' and len(witnessed)>1 and lower==1:
            diagnostics.append('EVENT_DISTINCTNESS_NOT_ESTABLISHED')
    if runtime is not None:
        runtime.rule('WINDOW_AGGREGATE',logical_depth=depth,detail=goal.count_unit+'; explicit window and domain')
    return outcome(status,proofs,tuple(dict.fromkeys(diagnostics)),CountConclusion(lower if witnessed or complete else None,exact,proofs,exact))
