"""Declared causal, temporal and ordered-value questions over native proofs.

Names never supply a measure, a causal relation, completeness or numeric value.
All search starts at the question's T/Ref indexes and shares its finite budget.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation

from ah.inference.contracts import NativeFormulaGoal, LogicalStatus, QuestionAnswerConclusion
from ah.model import Ref, RefKind
from .canonical_ledger import region, region_data
from .temporal_license import normalize, forall_inst_license, covers


def _spend(budget):
    budget[0]-=1
    if budget[0]<0:
        raise ValueError('COMPUTATION_LIMIT')


def _formula(goal,pattern=None):
    return NativeFormulaGoal(goal.pattern if pattern is None else pattern,goal.temporal_point,goal.temporal_window,
                             goal.workspace_refs,goal.source_scope)


def _released(adapter,goal):
    release=getattr(adapter,'resource_release',None)
    if release is None or release.sha256!=goal.resource_snapshot:
        raise ValueError('RESOURCE_MISSING: question resource snapshot')
    release.assert_integrity()
    return release


def _owner(pattern):
    from .native_queries import Pattern
    found=[]
    def walk(p):
        if not isinstance(p,Pattern): return
        if p.query_owner: found.append(p)
        for m in p.members: walk(m)
        for r,v in p.actants: walk(v)
    walk(pattern)
    if not found and getattr(pattern,'operator',None) is None: found=[pattern]
    if len(found)!=1: raise ValueError('QUERY_TARGET_UNBOUND')
    return found[0]


def solve_question(engine,adapter,ledger,goal,query,workspace,attention,context,runtime,budget,depth,outcome):
    if goal.kind=='WHEN':
        return _when(engine,adapter,ledger,goal,query,workspace,attention,context,runtime,budget,depth,outcome)
    if goal.kind=='WHY':
        return _why(engine,adapter,ledger,goal,query,workspace,attention,context,runtime,budget,depth,outcome)
    release=_released(adapter,goal)
    schemas=[s for s in release.resources.get('MeasureSchema',{}).get('entries',()) if s['measure_id']==goal.request['measure_id']]
    if len(schemas)!=1:
        raise ValueError('MEASURE_SCHEMA_MISSING')
    if goal.kind=='COMPARE':
        return _compare(engine,ledger,goal,schemas[0],query,workspace,attention,context,runtime,budget,depth,outcome)
    return _superlative(engine,release,ledger,goal,schemas[0],query,workspace,attention,context,runtime,budget,depth,outcome)


def _when(engine,adapter,ledger,goal,query,workspace,attention,context,runtime,budget,depth,outcome):
    from .native_queries import _matching_refs,_answers_window,solve_native_goal
    from .native_records import record_index
    from .native_scope import proof_ledger
    # Ask the same proof kernel first. Registered on-demand rules may supply
    # the requested fact; hypothetical witnesses remain purely runtime data.
    answer=solve_native_goal(engine,_formula(goal),query,workspace,attention,context,runtime,
                             _budget=budget,_depth=depth+1)
    if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
    ledger=proof_ledger(engine.core,adapter.ledger,context,goal,budget,(*workspace,*goal.workspace_refs))
    ids=set(_matching_refs(engine.core,ledger,goal.pattern,limit=min(4096,max(1,budget[0])),workspace=(*workspace,*goal.workspace_refs)))
    values=[]; refs=[]; conflicts=set()
    index=record_index(engine.core,ledger)
    for aid in sorted({aid for uid in ids for aid in index['targets'].get(uid,())}):
        _spend(budget)
        a=ledger.data['assertions'][aid]
        if a['target_ref'] not in ids or not ledger.evidence_live({'record_id':aid}):
            continue
        r=normalize(region(a['region']))
        if not _answers_window(r,goal): continue
        values.append({'target_ref':a['target_ref'],'assertion_id':aid,'region':region_data(r)})
        refs.append(engine.core.ref(a['target_ref']))
        conflicts.update(ledger.query(a['target_ref'])['conflict_ref'])
        if len(values)>1024: raise ValueError('COMPUTATION_LIMIT')
    if answer.status is LogicalStatus.PROVED:
        refs.extend(answer.premise_refs)
        for r in answer.temporal_regions:
            if r.kind!='UNDATED' and _answers_window(r,goal) and region_data(r) not in [v['region'] for v in values]:
                values.append({'region':region_data(r),'proof_refs':[r.uid for r in answer.premise_refs]})
    # EXISTENTIAL is deliberately returned as an unknown point in its interval.
    # The bounds describe knowledge, not a fabricated exact event timestamp.
    return outcome(LogicalStatus.PROVED if values else LogicalStatus.UNKNOWN,tuple(dict.fromkeys(refs)),
        tuple(dict.fromkeys((*answer.diagnostics,*('conflict_ref:'+r for r in sorted(conflicts)),*(() if values else ('TIME_EVIDENCE_ABSENT',))))),
        QuestionAnswerConclusion('WHEN',{'evidences':values},False))


def _why(engine,adapter,ledger,goal,query,workspace,attention,context,runtime,budget,depth,outcome):
    from .native_queries import _matching_refs,solve_native_goal,_answers_window
    from .native_derivations import pattern_from_ref,proof_regions
    refs=_matching_refs(engine.core,ledger,goal.pattern,limit=min(4096,max(1,budget[0])),workspace=(*workspace,*goal.workspace_refs))
    release=getattr(adapter,'resource_release',None)
    causal=release.resources.get('CausalSchema',{}).get('entries',()) if release is not None else ()
    if release is not None: release.assert_integrity()
    schema=engine.schema_registry.get('CAUSE')
    if 'CAUSE_MP' not in schema.rule_handlers:
        raise ValueError('CAUSE_RULE_NOT_REGISTERED')
    max_depth=query.max_depth or engine.settings.max_depth
    def incoming(uid):
        for declared in causal:
            for node in engine.core.store.find_hypernodes_by_template(declared['template_ref']):
                _spend(budget)
                actual=ledger.data['nodes'].get(node.uid,{}).get('actants',{})
                if actual.get(declared['effect_role'])!=uid:
                    continue
                source=actual.get(declared['cause_role'])
                if not isinstance(source,str) or source not in ledger.data['nodes']:
                    continue
                answer=ledger.query_proposition(node.uid,point=goal.temporal_point,window=goal.temporal_window)
                # Explicitly declared atemporal CAUSE rules can be undated. A
                # bare undated ordinary relationship is not made universal.
                if answer['answer']!='YES' and declared.get('temporal_policy')=='ATEMPORAL_RULE':
                    answer=ledger.query_proposition(node.uid)
                if answer['answer']=='YES':
                    rr=proof_regions(engine.core,ledger,(engine.core.ref(node.uid),),budget)
                    yield source,(engine.core.ref(node.uid),),rr,declared.get('temporal_policy','SAME_SCOPE')
        for link in engine.core.store.incoming_links(uid,'CAUSE'):
            _spend(budget)
            if link.source.kind not in {RefKind.N,RefKind.G}: continue
            # A legacy link without a live native grounding is only a candidate.
            # Its weight/existence cannot authorize CAUSE_MP in the new path.
            for support in engine.core.resolve_supports(engine.core.ref(link.uid)):
                if not support.premise_refs: continue
                if all(r.uid in ledger.data['nodes'] and ledger.query_proposition(r.uid,point=goal.temporal_point,window=goal.temporal_window)['answer']=='YES' for r in support.premise_refs):
                    rr=proof_regions(engine.core,ledger,support.premise_refs,budget)
                    yield link.source.uid,(engine.core.ref(link.uid),*support.premise_refs),rr,'SAME_SCOPE'
                    break
    def prove(uid,seen,level):
        if uid in seen or level>max_depth: return None
        for source,relation_refs,relationship_regions,policy in incoming(uid):
            pattern=pattern_from_ref(engine.core,ledger,source,budget)
            answer=solve_native_goal(engine,_formula(goal,pattern),query,workspace,attention,context,runtime,
                                     _budget=budget,_depth=depth+level+1)
            if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
            if answer.status is LogicalStatus.PROVED:
                premises=answer.premise_refs; source_regions=answer.temporal_regions
                path=[]
            else:
                earlier=prove(source,seen|{uid},level+1)
                if earlier is None: continue
                premises,source_regions,path=earlier
            licensed=[]
            for r in relationship_regions:
                for s in source_regions:
                    license=forall_inst_license(r,s)
                    derived=s if policy=='ATEMPORAL_RULE' and r.kind=='UNDATED' else license.derived_region if license.status=='LICENSED' else None
                    if derived is not None and _answers_window(normalize(derived),goal): licensed.append(derived)
            if not licensed: continue
            edge={'cause_ref':source,'effect_ref':uid,'relation_refs':[r.uid for r in relation_refs]}
            return tuple(dict.fromkeys((*premises,*relation_refs))),tuple(licensed),[*path,edge]
        return None
    for uid in refs:
        found=prove(uid,frozenset(),0)
        if found is None: continue
        premises,regions,path=found
        if runtime is not None: runtime.rule('CAUSE_MP',logical_depth=depth,detail='grounded native CAUSE chain')
        return outcome(LogicalStatus.PROVED,premises,('NATIVE_CAUSAL_EXPLANATION',),
                       QuestionAnswerConclusion('WHY',{'effect_ref':uid,'path':path},False),regions)
    return outcome(LogicalStatus.UNKNOWN,diagnostics=('NO_CAUSAL_SUPPORT',),
                   conclusion=QuestionAnswerConclusion('WHY',{'paths':[]},False))


def measured_values(core,ledger,entity,schema,goal,budget):
    from .native_queries import _answer_regions
    result=[]
    for node in core.store.find_hypernodes_by_template(schema['template_ref']):
        _spend(budget)
        actual=ledger.data['nodes'].get(node.uid,{}).get('actants',{})
        if actual.get(schema['subject_role'])!=entity.uid: continue
        if ledger.query_proposition(node.uid,point=goal.temporal_point,window=goal.temporal_window)['answer']!='YES': continue
        value_ref=actual.get(schema['value_role'])
        if not isinstance(value_ref,str) or not core.store.has_uid(value_ref) or core.store.kind_of(value_ref) is not RefKind.M: continue
        value_entity=core.store.get_element_any_domain(value_ref)
        prop=value_entity.properties.get(schema['numeric_property'])
        if prop is None or prop.unit!=schema['unit'] or type(prop.value) is bool: continue
        if type(prop.value) not in {int,float,str} or isinstance(prop.value,str) and prop.type_name.lower() not in {'number','float','integer','decimal','int','double'}: continue
        try: number=Decimal(str(prop.value))
        except (InvalidOperation,ValueError): continue
        if not number.is_finite(): continue
        regions=_answer_regions(ledger,node.uid,goal,core=core)
        result.append((number,core.ref(node.uid),regions))
        if len(result)>1024: raise ValueError('COMPUTATION_LIMIT')
    return result


def _compare(engine,ledger,goal,schema,query,workspace,attention,context,runtime,budget,depth,outcome):
    from .native_queries import Pattern,solve_native_goal,_answers_window
    from .native_scope import query_region
    owner=_owner(goal.pattern)
    left=dict(owner.actants).get(next(r for r,v in owner.actants if r.value==schema['subject_role'])) if any(r.value==schema['subject_role'] for r,v in owner.actants) else None
    uid=goal.request.get('compare_entity_ref')
    if not isinstance(left,Ref) or left.kind is not RefKind.M or not engine.core.store.has_uid(uid) or engine.core.store.kind_of(uid) is not RefKind.M:
        raise ValueError('QUERY_ENTITY_UNBOUND')
    right=engine.core.ref(uid)
    first=measured_values(engine.core,ledger,left,schema,goal,budget)
    second=measured_values(engine.core,ledger,right,schema,goal,budget)
    ordering=goal.request.get('ordering','GT'); observations=[]; refs=[]; regions=[]
    for a,ar,aa in first:
        for b,br,bb in second:
            _spend(budget)
            value={'GT':a>b,'LT':a<b,'EQ':a==b,'GE':a>=b,'LE':a<=b,'NE':a!=b}[ordering]
            for ra in aa:
                for rb in bb:
                    license=forall_inst_license(ra,rb)
                    if license.status!='LICENSED' or not _answers_window(normalize(license.derived_region),goal): continue
                    # A negative pair at one unknown point does not refute an
                    # existential comparison over an entire requested window.
                    if not value and goal.temporal_window is not None and covers(license.derived_region,query_region(goal)) is not True: continue
                    observations.append(value); refs.extend((ar,br)); regions.append(license.derived_region)
    status=LogicalStatus.UNKNOWN
    if observations and len(set(observations))==1:
        status=LogicalStatus.PROVED if observations[0] else LogicalStatus.DISPROVED
    def contains_owner(p):
        return isinstance(p,Pattern) and (p is owner or any(contains_owner(m) for m in p.members) or any(contains_owner(v) for r,v in p.actants))
    def value_gap_only(p,variable):
        from ah.model import BoundVar
        if isinstance(p,BoundVar): return p.local_id!=variable.local_id
        if not isinstance(p,Pattern): return True
        return all(value_gap_only(m,variable) for m in p.members) and all(
            p is owner and r.value==schema['value_role'] or value_gap_only(v,variable) for r,v in p.actants)
    def full(p,level=0):
        _spend(budget)
        if level>engine.settings.max_depth: raise ValueError('COMPUTATION_LIMIT')
        if p is owner: return status,tuple(dict.fromkeys(refs))
        if not isinstance(p,Pattern): return LogicalStatus.UNKNOWN,()
        if p.operator in {'AND','OR','XOR','NOT'}:
            children=[full(m,level+1) for m in p.members]; statuses=[s for s,r in children]
            evidence=tuple(dict.fromkeys(r for s,rr in children for r in rr))
            if p.operator=='NOT' and len(statuses)==1:
                return ({LogicalStatus.PROVED:LogicalStatus.DISPROVED,LogicalStatus.DISPROVED:LogicalStatus.PROVED}.get(statuses[0],LogicalStatus.UNKNOWN),evidence)
            yes=statuses.count(LogicalStatus.PROVED); no=statuses.count(LogicalStatus.DISPROVED)
            if p.operator=='AND': s=LogicalStatus.DISPROVED if no else LogicalStatus.PROVED if yes==len(statuses) else LogicalStatus.UNKNOWN
            elif p.operator=='OR': s=LogicalStatus.PROVED if yes else LogicalStatus.DISPROVED if no==len(statuses) else LogicalStatus.UNKNOWN
            else: s=LogicalStatus.PROVED if yes==1 and no==len(statuses)-1 else LogicalStatus.DISPROVED if yes>1 or no==len(statuses) else LogicalStatus.UNKNOWN
            # Correlation of independent window claims is not established.
            if p.operator=='AND' and goal.temporal_window is not None and s is LogicalStatus.PROVED:
                s=LogicalStatus.UNKNOWN
            return s,evidence
        if p.operator=='EXISTS' and len(p.members)==2 and contains_owner(p.members[1]) and value_gap_only(p.members[1],p.members[0]):
            # This is the compiler's omitted measure-value slot. Comparing
            # actual values itself supplies that existential witness; never
            # replace the comparison with a bare 'measurement exists' proof.
            return full(p.members[1],level+1)
        if contains_owner(p): return LogicalStatus.UNKNOWN,()
        answer=solve_native_goal(engine,_formula(goal,p),query,workspace,attention,context,runtime,_budget=budget,_depth=depth+1)
        if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
        return answer.status,answer.premise_refs
    final,proofs=full(goal.pattern)
    diagnostics=('CONFLICTING_MEASURES',) if len(set(observations))>1 else () if observations else ('COMPARABLE_MEASURES_ABSENT',)
    return outcome(final,proofs,diagnostics,QuestionAnswerConclusion('COMPARE',{
        'measure_id':schema['measure_id'],'unit':schema['unit'],'left_ref':left.uid,'right_ref':right.uid,'ordering':ordering,
        'left_values':[str(x[0]) for x in first],'right_values':[str(x[0]) for x in second]},bool(observations)),regions)


def _superlative(engine,release,ledger,goal,schema,query,workspace,attention,context,runtime,budget,depth,outcome):
    from .query_bindings import candidate_values,substitute,pattern_signature
    from .native_queries import solve_native_goal
    from .native_scope import proof_ledger
    variable=goal.request['requested_roles'][0]
    candidates=candidate_values(engine.core,ledger,goal.pattern,(variable,),budget,context=context)[variable]
    rows={}; evidence=[]; unresolved=False; scopes={}
    for uid in sorted(candidates):
        entity=engine.core.ref(uid)
        if entity.kind is not RefKind.M: continue
        answer=solve_native_goal(engine,_formula(goal,substitute(goal.pattern,{variable:entity})),query,workspace,attention,context,runtime,_budget=budget,_depth=depth+1)
        if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
        if answer.status is LogicalStatus.UNKNOWN: unresolved=True
        if answer.status is not LogicalStatus.PROVED: continue
        ledger=proof_ledger(engine.core,engine.core._formalizer_adapter.ledger,context,goal,budget,(*workspace,*goal.workspace_refs))
        values=measured_values(engine.core,ledger,entity,schema,goal,budget)
        unique={v for v,r,t in values}
        if len(unique)!=1:
            unresolved=True; continue
        rows[uid]=next(iter(unique))
        scopes[uid]=tuple(dict.fromkeys(t for v,r,tt in values for t in tt))
        evidence.extend((*answer.premise_refs,*(r for v,r,t in values)))
        # A maximum across objects needs a common comparison scope. For a
        # window each measurement must hold throughout it; existential times
        # at unrelated points cannot certify a simultaneous global maximum.
        if goal.temporal_window is not None:
            from .native_scope import query_region
            if not any(covers(t,query_region(goal)) is True for v,r,tt in values for t in tt): unresolved=True
    # An undated question still cannot combine measurements at disjoint
    # moments. Preserve a licensed common region in the runtime answer.
    common=()
    for uid in sorted(rows):
        if not common:
            common=scopes[uid]
        else:
            merged=[]
            for a in common:
                for b in scopes[uid]:
                    _spend(budget)
                    license=forall_inst_license(a,b)
                    if license.status=='LICENSED':
                        r=normalize(license.derived_region)
                        if r not in merged: merged.append(r)
                    if len(merged)>64: raise ValueError('COMPUTATION_LIMIT')
            common=tuple(merged)
        if not common: break
    incompatible=bool(rows) and not common
    unresolved |= incompatible
    complete=False; signature=pattern_signature(goal.pattern)
    window=[goal.temporal_point,goal.temporal_point] if goal.temporal_point is not None else list(goal.temporal_window) if goal.temporal_window is not None else None
    paths=ledger.paths()
    if not unresolved and not context.is_counterfactual():
        for cert in release.resources.get('ComparisonDomainCertificate',{}).get('entries',()):
            if (cert['pattern_signature']==signature and cert['variable']==variable and cert['measure_id']==schema['measure_id']
                    and cert['request_window']==window and set(cert['member_refs'])==set(rows)
                    and (goal.request.get('domain_certificate') is None or cert['domain_id']==goal.request['domain_certificate'])
                    and all(s in paths for s in cert['completeness_evidence'])):
                complete=True
                evidence.extend(engine.core.ref(ledger.data['supports'][s]['conclusion_ref']) for s in cert['completeness_evidence'])
                break
    ordering=goal.request.get('ordering','MAX')
    best=(max(rows.values()) if ordering=='MAX' else min(rows.values())) if rows else None
    winners=[uid for uid,v in sorted(rows.items()) if v==best] if not incompatible else []
    return outcome(LogicalStatus.PROVED if winners and complete else LogicalStatus.UNKNOWN,
        tuple(dict.fromkeys(evidence)),() if complete else (('COMPARISON_SCOPE_NOT_ESTABLISHED','INCOMPLETE_COMPARISON_DOMAIN') if incompatible else ('INCOMPLETE_COMPARISON_DOMAIN',)),
        QuestionAnswerConclusion('SUPERLATIVE',{'measure_id':schema['measure_id'],'unit':schema['unit'],
            'ordering':ordering,'candidate_refs':winners,'value':str(best) if best is not None else None,
            'pattern_signature':signature,'comparison_regions':[region_data(r) for r in common]},complete))
