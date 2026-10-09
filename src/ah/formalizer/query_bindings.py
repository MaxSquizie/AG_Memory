"""Bounded indexed gap search; every returned binding proves the whole formula."""
from __future__ import annotations
from dataclasses import replace
from itertools import product
from ah.model import Ref,RefKind,BoundVar,TimeLiteral,CountLiteral,VariableSort
from ah.inference.contracts import NativeFormulaGoal,NativeBindingsConclusion,CountConclusion,LogicalStatus
from .canonical_ledger import digest


def pattern_signature(pattern):
    """Typed formula/gap signature independent of surface frame IDs."""
    from .native_queries import Pattern,QueryVar
    variables={}
    def encode(p):
        if isinstance(p,Ref): return {'ref':p.uid,'kind':p.kind.value}
        if isinstance(p,QueryVar): return {'query_var':p.name,'sort':p.sort.value}
        if isinstance(p,BoundVar): return {'bound_var':variables.setdefault(p.local_id,len(variables)),'sort':p.sort.value}
        if isinstance(p,TimeLiteral): return {'time_literal':list(p.bounds)}
        if isinstance(p,CountLiteral): return {'count_literal':p.value}
        if not isinstance(p,Pattern): raise ValueError('QUERY_TARGET_UNBOUND')
        members=[encode(m) for m in p.members]
        if p.operator in {'AND','OR','XOR'}: members.sort(key=digest)
        return {'operator':p.operator,'members':members,'template_ref':p.template_ref,
                **({'occurrence_ref':p.occurrence_ref} if p.occurrence_ref is not None else {}),
                'actants':[[r.value,encode(v)] for r,v in sorted(p.actants,key=lambda pair:pair[0].value)],
                'lexical_anchor':p.lexical_anchor,'temporal':p.temporal}
    return digest({'format':'native-query-pattern-v1','pattern':encode(pattern)})


def substitute(pattern,bindings,*,bound=False):
    from .native_queries import Pattern,QueryVar
    if isinstance(pattern,QueryVar) and not bound: return bindings.get(pattern.name,pattern)
    if isinstance(pattern,BoundVar) and bound: return bindings.get(pattern.local_id,pattern)
    if not isinstance(pattern,Pattern): return pattern
    local=bindings
    if bound and pattern.operator in {'FORALL','EXISTS','AT_LEAST_N','EXACTLY_N','AT_MOST_N'} and pattern.members and isinstance(pattern.members[0],BoundVar):
        local={k:v for k,v in bindings.items() if k!=pattern.members[0].local_id}
    return replace(pattern,members=tuple(substitute(m,local,bound=bound) for m in pattern.members),
                   actants=tuple((r,substitute(v,local,bound=bound)) for r,v in pattern.actants))


def candidate_values(core,ledger,pattern,names,budget,*,bound=False,context=None,_depth=0,_seen=frozenset()):
    """Candidates overapproximate results; no candidate is itself a truth proof."""
    from .native_queries import Pattern,QueryVar
    values={name:set() for name in names}; typ=BoundVar if bound else QueryVar
    key=(pattern_signature(pattern),tuple(sorted(names)),bound)
    if key in _seen: return values
    if _depth>16: raise ValueError('COMPUTATION_LIMIT')
    seen=_seen|{key}
    def spend():
        budget[0]-=1
        if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
    def walk(p,active):
        if not isinstance(p,Pattern): return
        if p.operator is None and not p.lexical_anchor:
            gaps=[(r,v.local_id if bound else v.name,v.sort) for r,v in p.actants if isinstance(v,typ) and (v.local_id if bound else v.name) in active]
            if gaps:
                indexed_rules=None
                for n in core.store.find_hypernodes_by_template(p.template_ref):
                    spend()
                    actual=ledger.data['nodes'].get(n.uid,{}).get('actants',{})
                    if any(isinstance(v,Ref) and not isinstance(actual.get(r.value),dict) and actual.get(r.value)!=v.uid for r,v in p.actants): continue
                    for role,name,sort in gaps:
                        uid=actual.get(role.value)
                        if isinstance(uid,str) and core.store.has_uid(uid) and core.store.kind_of(uid) in ({RefKind.M} if bound or sort is VariableSort.ENTITY else {RefKind.M,RefKind.N,RefKind.G}):
                            values[name].add(uid)
                            if len(values[name])>1024: raise ValueError('COMPUTATION_LIMIT')
                    symbolic={name:actual[role.value]['bound_var'] for role,name,sort in gaps
                              if isinstance(actual.get(role.value),dict) and 'bound_var' in actual[role.value]}
                    if not symbolic: continue
                    # Enumerate from a universal's restriction even before its
                    # consequent is materialized. Final full-body proof still
                    # checks every role, live premise and temporal license.
                    from .native_derivations import pattern_from_ref
                    adapter=getattr(core,'_formalizer_adapter',None)
                    if adapter is None: continue
                    from .goal_queries import Search
                    if indexed_rules is None:
                        search=Search(adapter,budget)
                        indexed_rules=search._rules({'template_ref':p.template_ref,'actants':{}})
                    for root_id,variables,body_id in indexed_rules:
                        spend()
                        if not set(symbolic.values())<=set(variables) or not ledger.f_visible(root_id): continue
                        impl=ledger.data['nodes'].get(body_id,{})
                        if impl.get('function_id')!='IMPLIES': continue
                        # A head can be an AND projection; candidate discovery
                        # follows the same registered projections as the writer.
                        if not any(head==n.uid for head,path in search._heads(impl['operands'][1])): continue
                        restriction=pattern_from_ref(core,ledger,impl['operands'][0],budget)
                        bound_values=candidate_values(core,ledger,restriction,tuple(sorted(set(symbolic.values()))),budget,
                                                      bound=True,context=context,_depth=_depth+1,_seen=seen)
                        for name,var in symbolic.items():
                            values[name].update(bound_values[var])
                            if len(values[name])>1024: raise ValueError('COMPUTATION_LIMIT')
                if context is not None:
                    from .native_scope import overrides
                    for assumption in overrides(context):
                        spend(); a=assumption.pattern
                        if not assumption.positive or not isinstance(a,Pattern): continue
                        if a.operator=='FORALL' and len(a.members)==2:
                            rule=a.members[1]
                            if not isinstance(rule,Pattern) or rule.operator!='IMPLIES' or len(rule.members)!=2: continue
                            antecedent,consequent=rule.members
                            if not isinstance(consequent,Pattern) or consequent.operator is not None or consequent.template_ref!=p.template_ref: continue
                            actual=dict(consequent.actants)
                            symbolic={name:actual[role].local_id for role,name,sort in gaps if isinstance(actual.get(role),BoundVar)}
                            if symbolic:
                                bound_values=candidate_values(core,ledger,antecedent,tuple(sorted(set(symbolic.values()))),budget,
                                                              bound=True,context=context,_depth=_depth+1,_seen=seen)
                                for name,var in symbolic.items():
                                    values[name].update(bound_values[var])
                                    if len(values[name])>1024: raise ValueError('COMPUTATION_LIMIT')
                            continue
                        if a.operator is not None or a.template_ref!=p.template_ref: continue
                        actual={r.value:v for r,v in a.actants}
                        if any(isinstance(v,Ref) and actual.get(r.value)!=v for r,v in p.actants): continue
                        for role,name,sort in gaps:
                            value=actual.get(role.value)
                            if isinstance(value,Ref) and value.kind in ({RefKind.M} if bound or sort is VariableSort.ENTITY else {RefKind.M,RefKind.N,RefKind.G}):
                                values[name].add(value.uid)
                                if len(values[name])>1024: raise ValueError('COMPUTATION_LIMIT')
        nested=active
        if bound and p.operator in {'FORALL','EXISTS','AT_LEAST_N','EXACTLY_N','AT_MOST_N'} and p.members and isinstance(p.members[0],BoundVar):
            nested=active-{p.members[0].local_id}
        for child in p.members: walk(child,nested)
        for role,child in p.actants: walk(child,active)
    walk(pattern,set(names))
    return values


def formula_numeric_bounds(core,ledger,goal,budget):
    """Match the entire restricted count body, including every nested scope."""
    from .native_queries import Pattern,_matching_refs,_uniform_windows
    if goal.temporal_window is not None or not _uniform_windows(goal.pattern,goal): return None,None,()
    used=set()
    def variables(p):
        if isinstance(p,BoundVar): used.add(p.local_id)
        elif isinstance(p,Pattern):
            for m in p.members: variables(m)
            for r,v in p.actants: variables(v)
    variables(goal.pattern)
    variable=BoundVar(max(used,default=-1)+1,VariableSort.ENTITY)
    body=substitute(goal.pattern,{goal.variables[0]:variable})
    bodies=_matching_refs(core,ledger,body,limit=min(4096,max(1,budget[0])))
    lower=None; upper=None; proofs=[]; paths=ledger.paths()
    for uid in bodies:
        for root in core.store.function_parents(uid):
            budget[0]-=1
            if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
            claim=ledger.data['nodes'].get(root.uid,{})
            op=claim.get('function_id'); operands=claim.get('operands',())
            if op not in {'AT_LEAST_N','EXACTLY_N','AT_MOST_N'} or len(operands)!=3 or operands[1]!=uid: continue
            value=operands[2].get('count_literal') if isinstance(operands[2],dict) else None
            if type(value) is not int: raise ValueError('INTEGRITY_ERROR: invalid count literal')
            match=Pattern(op,(variable,body,CountLiteral(value)))
            if not _matching_refs(core,ledger,match,limit=min(4096,max(1,budget[0])),target_uid=root.uid): continue
            if goal.temporal_point is None and not any(s['conclusion_ref']==root.uid and sid in paths
                    and not any(a['support_record_id']==sid for a in ledger.data['assertions'].values())
                    for sid,s in ledger.data['supports'].items()): continue
            if ledger.query(root.uid,point=goal.temporal_point)['answer']!='YES': continue
            if op in {'AT_LEAST_N','EXACTLY_N'}: lower=value if lower is None else max(lower,value)
            if op in {'AT_MOST_N','EXACTLY_N'}: upper=value if upper is None else min(upper,value)
            proofs.append(core.ref(root.uid))
    return lower,upper,tuple(dict.fromkeys(proofs))


def solve_bindings(engine,adapter,goal,query,workspace,attention,context,runtime,budget,depth,outcome,*,ledger=None):
    from .native_queries import solve_native_goal
    ledger=ledger or adapter.ledger
    values=candidate_values(engine.core,ledger,goal.pattern,goal.variables,budget,context=context)
    rows=[]; refs=[]; diagnostics=[]
    for i,combo in enumerate(product(*(sorted(values[v]) for v in goal.variables))):
        if i>=1024: raise ValueError('COMPUTATION_LIMIT')
        binding={v:engine.core.ref(uid) for v,uid in zip(goal.variables,combo)}
        target=NativeFormulaGoal(substitute(goal.pattern,binding),goal.temporal_point,goal.temporal_window,goal.workspace_refs,goal.source_scope)
        answer=solve_native_goal(engine,target,query,workspace,attention,context,runtime,_budget=budget,_depth=depth+1)
        diagnostics.extend(answer.diagnostics)
        if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
        if answer.status is LogicalStatus.PROVED:
            rows.append(tuple(binding[v] for v in goal.variables)); refs.extend(answer.premise_refs)
    refs=tuple(dict.fromkeys(refs)); signature=pattern_signature(goal.pattern)
    if goal.mode=='WH':
        return outcome(LogicalStatus.PROVED if rows else LogicalStatus.UNKNOWN,refs,
                       tuple(dict.fromkeys(diagnostics)),NativeBindingsConclusion(goal.variables,tuple(rows),signature))
    claimed_lower,claimed_upper,bound_refs=formula_numeric_bounds(engine.core,ledger,goal,budget)
    lower=max(len(rows),claimed_lower or 0); refs=tuple(dict.fromkeys((*refs,*bound_refs)))
    release=getattr(adapter,'resource_release',None); complete=False; closure_mode='ENUMERATED'
    window=[goal.temporal_point,goal.temporal_point] if goal.temporal_point is not None else list(goal.temporal_window) if goal.temporal_window is not None else None
    if release is not None and release.sha256==goal.resource_snapshot and not context.is_counterfactual() and not goal.source_scope:
        paths=ledger.paths(); release.assert_integrity()
        for cert in release.resources.get('FormulaDomainCertificate',{}).get('entries',()):
            if (cert['pattern_signature']==signature and cert['count_variable']==goal.variables[0]
                    and cert['request_window']==window
                    and (goal.domain_certificate is None or cert['domain_id']==goal.domain_certificate)
                    and all(s in paths for s in cert['completeness_evidence'])):
                closure_mode=cert.get('closure_mode','ENUMERATED')
                complete=closure_mode=='ENUMERATED' or claimed_lower is not None and claimed_lower==claimed_upper
                if not complete: continue
                refs=tuple(dict.fromkeys((*refs,*(engine.core.ref(ledger.data['supports'][s]['conclusion_ref']) for s in cert['completeness_evidence']))))
                break
    count=claimed_lower if complete and closure_mode=='ASSERTED_BOUND' else len(rows)
    if claimed_upper is not None and lower>claimed_upper or complete and lower>count:
        return outcome(LogicalStatus.UNKNOWN,refs,('COUNT_BOUNDS_CONFLICT',),CountConclusion(lower,None,refs,claimed_upper))
    status=LogicalStatus.UNKNOWN; n=goal.expected_count
    if complete:
        valid=n is None or (count==n if goal.comparison=='EXACTLY_N' else count>=n if goal.comparison=='AT_LEAST_N' else count<=n)
        status=LogicalStatus.PROVED if valid else LogicalStatus.DISPROVED
    elif n is not None:
        if goal.comparison=='AT_LEAST_N' and lower>=n: status=LogicalStatus.PROVED
        elif goal.comparison in {'EXACTLY_N','AT_MOST_N'} and lower>n: status=LogicalStatus.DISPROVED
    return outcome(status,refs,tuple(dict.fromkeys([*diagnostics,*(() if complete else ('INCOMPLETE_DOMAIN',))])),
                   CountConclusion(lower,count if complete else None,refs,count if complete else claimed_upper))
