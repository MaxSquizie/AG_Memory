"""Registered rules in a temporary proof scope; never call the goal writer."""
from dataclasses import replace
from itertools import product

from ah.inference.contracts import NativeFormulaGoal, LogicalStatus, FormulaQueryConclusion
from ah.model import Ref, BoundVar, VariableSort, TimeLiteral, CountLiteral

from .canonical_ledger import region
from .temporal_license import normalize, or_elimination_license, forall_inst_license
from .inference_policy import node_inference_policy


def pattern_from_ref(core, ledger, uid, budget, depth=0):
    from .native_queries import Pattern
    budget[0] -= 1
    if budget[0] < 0 or depth > 32:
        raise ValueError('COMPUTATION_LIMIT')
    node = ledger.data['nodes'].get(uid)
    if node is None:
        raise ValueError('QUERY_TARGET_UNBOUND')
    def operand(value):
        if isinstance(value, dict):
            if 'bound_var' in value:
                return BoundVar(value['bound_var'], VariableSort(value.get('sort','ENTITY')))
            if 'time_literal' in value:
                return TimeLiteral(tuple(value['time_literal']))
            if 'count_literal' in value:
                return CountLiteral(value['count_literal'])
            raise ValueError('QUERY_TARGET_UNBOUND')
        ref = core.ref(value)
        return pattern_from_ref(core, ledger, value, budget, depth+1) if ref.kind.value in {'N','G'} else ref
    if node.get('function_id'):
        return Pattern(node['function_id'], tuple(operand(x) for x in node['operands']))
    if node_inference_policy(node).exact_attestation_only:
        raise ValueError('OPEN_LEXICAL_INFERENCE_FORBIDDEN')
    from ah.model import ActantRole
    return Pattern(template_ref=node['template_ref'],
                   actants=tuple((ActantRole(r), operand(v)) for r,v in sorted(node['actants'].items())))


def proof_regions(core, ledger, refs, budget):
    """Every option keeps its concrete support/assertion, not only a node UID."""
    from .native_records import record_index
    paths = ledger.paths(); index=record_index(core,ledger)
    groups = []
    for ref in refs:
        options=[]
        for sid in index['supports'].get(ref.uid,()):
            budget[0] -= 1
            if budget[0] < 0:
                raise ValueError('COMPUTATION_LIMIT')
            if sid not in paths:
                continue
            assertion_ids=index['assertions'].get(sid,())
            dated = [region(ledger.data['assertions'][aid]['region']) for aid in assertion_ids
                     if ledger.evidence_live({'record_id':aid})]
            # Retraction of a dated witness never turns its path into an
            # undated proposition or restores an expired temporal license.
            options.extend(dated if assertion_ids else [region()])
            if len(options)>64:
                raise ValueError('COMPUTATION_LIMIT')
        groups.append(options)
    if not groups: return []
    common=groups[0]
    for options in groups[1:]:
        merged=[]
        for a,b in product(common,options):
            budget[0]-=1
            if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
            license=forall_inst_license(a,b)
            if license.status=='LICENSED' and license.derived_region not in merged:
                merged.append(license.derived_region)
            if len(merged)>64: raise ValueError('COMPUTATION_LIMIT')
        common=merged
    return common


def unify_pattern(symbolic, ground, budget, bindings=None):
    """Bind rule variables to typed ground operands, retaining full content."""
    from .native_queries import Pattern
    result={} if bindings is None else dict(bindings)
    def match(a,b):
        budget[0]-=1
        if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
        if isinstance(a,BoundVar):
            if not isinstance(b,Ref) or a.sort is VariableSort.ENTITY and b.kind.value!='M': return False
            return result.setdefault(a.local_id,b)==b
        if not isinstance(a,Pattern): return a==b
        if not isinstance(b,Pattern) or a.operator!=b.operator or a.template_ref!=b.template_ref or a.lexical_anchor!=b.lexical_anchor: return False
        if a.operator in {'AND','OR','XOR'}:
            # Canonical order of typed members, then bounded multiset matching.
            def pair(left,right):
                if not left: return True
                for i,v in enumerate(right):
                    previous=dict(result)
                    if match(left[0],v) and pair(left[1:],right[:i]+right[i+1:]): return True
                    result.clear(); result.update(previous)
                return False
            return len(a.members)==len(b.members) and pair(list(a.members),list(b.members))
        aa=dict(a.actants); bb=dict(b.actants)
        return set(aa)==set(bb) and len(a.members)==len(b.members) and all(match(x,y) for x,y in zip(a.members,b.members)) and all(match(aa[r],bb[r]) for r in aa)
    return result if match(symbolic,ground) else None


def runtime_derivation(engine, ledger, goal, query, workspace, attention, context, runtime, budget, depth):
    from .native_queries import Pattern, _matching_refs, _answers_window, solve_native_goal
    from .query_bindings import substitute
    from .native_scope import overrides, content_signature
    target = goal.pattern
    if target.lexical_anchor:
        return None
    for assumption in overrides(context):
        root=assumption.pattern
        if not assumption.positive: continue
        bindings={}; variable=None; implication=root
        if root.operator=='FORALL' and len(root.members)==2 and isinstance(root.members[0],BoundVar):
            variable,implication=root.members
        if implication.operator!='IMPLIES' or len(implication.members)!=2: continue
        antecedent,consequent=implication.members
        bindings=unify_pattern(consequent,target,budget)
        if bindings is None or variable is not None and variable.local_id not in bindings: continue
        if variable is None and bindings: continue
        antecedent=substitute(antecedent,bindings,bound=True)
        answer=solve_native_goal(engine,replace(goal,pattern=antecedent),query,workspace,attention,context,runtime,
                                 _budget=budget,_depth=depth+1)
        if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
        if answer.status is not LogicalStatus.PROVED: continue
        for r in answer.temporal_regions:
            license=forall_inst_license(assumption.temporal,r)
            if license.status=='LICENSED' and _answers_window(normalize(license.derived_region),goal):
                return answer.premise_refs,('FORALL_INST_RUNTIME' if variable is not None else 'MODUS_PONENS_RUNTIME'),normalize(license.derived_region)
    target_refs = _matching_refs(engine.core, ledger, target, limit=min(4096,max(1,budget[0])), workspace=workspace)
    for uid in target_refs:
        for parent in engine.core.store.function_parents(uid):
            budget[0]-=1
            if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
            spec=ledger.data['nodes'].get(parent.uid,{})
            root_regions=proof_regions(engine.core,ledger,(engine.core.ref(parent.uid),),budget)
            if spec.get('function_id')=='AND' and root_regions:
                for r in root_regions:
                    if _answers_window(normalize(r),goal):
                        return (engine.core.ref(parent.uid),),'AND_ELIMINATION_RUNTIME',normalize(r)
            if spec.get('function_id')=='IMPLIES' and spec['operands'][1]==uid and root_regions:
                antecedent=pattern_from_ref(engine.core,ledger,spec['operands'][0],budget)
                answer=solve_native_goal(engine,replace(goal,pattern=antecedent),query,workspace,attention,context,runtime,
                                         _budget=budget,_depth=depth+1)
                if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
                if answer.status is not LogicalStatus.PROVED: continue
                for a,b in product(root_regions,answer.temporal_regions):
                    budget[0]-=1
                    if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
                    license=forall_inst_license(a,b)
                    if license.status=='LICENSED' and _answers_window(normalize(license.derived_region),goal):
                        return tuple(dict.fromkeys((engine.core.ref(parent.uid),*answer.premise_refs))),'MODUS_PONENS_RUNTIME',normalize(license.derived_region)
    disjunctions = {}
    for uid in target_refs:
        for parent in engine.core.store.function_parents(uid):
            budget[0] -= 1
            if budget[0]<0:
                raise ValueError('COMPUTATION_LIMIT')
            if parent.function_id=='OR':
                try:
                    disjunctions[parent.uid]=(pattern_from_ref(engine.core,ledger,parent.uid,budget), proof_regions(engine.core,ledger,(engine.core.ref(parent.uid),),budget), (engine.core.ref(parent.uid),))
                except ValueError as exc:
                    if str(exc)!='OPEN_LEXICAL_INFERENCE_FORBIDDEN':
                        raise
    for i,a in enumerate(overrides(context)):
        if a.positive and getattr(a.pattern,'operator',None)=='OR':
            disjunctions['assumption:'+str(i)]=(a.pattern,[a.temporal],())
    for root, root_regions, root_refs in disjunctions.values():
        own = [i for i,p in enumerate(root.members) if content_signature(p)==content_signature(target)]
        if not own:
            continue
        remaining=[p for i,p in enumerate(root.members) if i!=own[0]]
        proofs=[]; region_options=[]
        for p in remaining:
            negated=Pattern('NOT',(p,))
            answer=solve_native_goal(engine,replace(goal,pattern=negated),query,workspace,attention,context,runtime,
                                     _budget=budget,_depth=depth+1)
            if 'COMPUTATION_LIMIT' in answer.diagnostics:
                raise ValueError('COMPUTATION_LIMIT')
            if answer.status is not LogicalStatus.PROVED:
                break
            regions=list(answer.temporal_regions)
            proofs.append(answer); region_options.append(regions)
        else:
            for i, combo in enumerate(product(root_regions,*region_options)):
                budget[0]-=1
                if i>=64 or budget[0]<0:
                    raise ValueError('COMPUTATION_LIMIT')
                if (all(or_elimination_license(combo[0],r).status=='LICENSED' for r in combo[1:])
                        and _answers_window(normalize(combo[0]),goal)):
                    refs=tuple(dict.fromkeys((*root_refs,*(r for p in proofs for r in p.premise_refs))))
                    return refs,'OR_ELIMINATION_RUNTIME',normalize(combo[0])
    # A ground consequent selects its symbolic T/body through existing reverse
    # indexes. The consequent is unified first; restriction stays in antecedent.
    if target.operator is not None or not all(isinstance(v,Ref) for r,v in target.actants):
        return None
    for symbolic in engine.core.store.find_hypernodes_by_template(target.template_ref):
        budget[0]-=1
        if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
        spec=ledger.data['nodes'].get(symbolic.uid,{})
        actual=spec.get('actants',{})
        if set(actual)!={r.value for r,v in target.actants}:
            continue
        bindings={}; variable_ids=set(); matched=True
        for role,value in target.actants:
            raw=actual[role.value]
            if isinstance(raw,dict) and 'bound_var' in raw:
                variable_ids.add(raw['bound_var'])
                if bindings.setdefault(raw['bound_var'],value)!=value:
                    matched=False
            elif raw!=value.uid:
                matched=False
        if not matched or len(variable_ids)!=1:
            continue
        for implication in engine.core.store.function_parents(symbolic.uid):
            budget[0]-=1
            if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
            impl=ledger.data['nodes'].get(implication.uid,{})
            if impl.get('function_id')!='IMPLIES' or impl['operands'][1]!=symbolic.uid:
                continue
            for universal in engine.core.store.function_parents(implication.uid):
                budget[0]-=1
                if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
                root=ledger.data['nodes'].get(universal.uid,{})
                if root.get('function_id')!='FORALL' or root['operands'][1]!=implication.uid:
                    continue
                var=root['operands'][0]
                if not isinstance(var,dict) or var.get('bound_var') not in variable_ids:
                    continue
                root_ref=engine.core.ref(universal.uid)
                root_regions=proof_regions(engine.core,ledger,(root_ref,),budget)
                antecedent=substitute(pattern_from_ref(engine.core,ledger,impl['operands'][0],budget),bindings,bound=True)
                answer=solve_native_goal(engine,replace(goal,pattern=antecedent),query,workspace,attention,context,runtime,
                                         _budget=budget,_depth=depth+1)
                if 'COMPUTATION_LIMIT' in answer.diagnostics:
                    raise ValueError('COMPUTATION_LIMIT')
                if answer.status is not LogicalStatus.PROVED:
                    continue
                ant_regions=list(answer.temporal_regions)
                for i,(a,b) in enumerate(product(root_regions,ant_regions)):
                    budget[0]-=1
                    if i>=64 or budget[0]<0:
                        raise ValueError('COMPUTATION_LIMIT')
                    license=forall_inst_license(a,b)
                    if license.status=='LICENSED' and _answers_window(normalize(license.derived_region),goal):
                        return tuple(dict.fromkeys((root_ref,*answer.premise_refs))),'FORALL_INST_RUNTIME',normalize(license.derived_region)
    return None
