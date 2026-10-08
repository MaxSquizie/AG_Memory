"""One read-only compiler for sealed native question trees and narrow AH reads.

Logical/quantified/modal shape is retained. Missing entities, senses or evidence
produce UNKNOWN; query compilation never manufactures a canonical proposition.
Only registered OR_ELIMINATION/FORALL_INST may write through the goal channel.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from itertools import product,islice
import re
from ah.model import ActantRole,Ref,RefKind,BoundVar,TimeLiteral,VariableSort,CountLiteral
from ah.inference.contracts import (NativeFormulaGoal,NativeBindingGoal,NativeBindingsConclusion,CountGoal,CountConclusion,
    ExistsGoal,RoleFillGoal,MultiRoleFillGoal,InferenceQuery,GoalSpec,LogicalStatus,
    StopReason,InferenceOutcome,ExistingRefConclusion,ProofSupport,
    AssociationGoal,TemporalComparisonConclusion,FormulaQueryConclusion)
from .canonical_ledger import digest,region
from .temporal_license import normalize,covers,TemporalRegion


@dataclass(frozen=True)
class NativeQueryRoot:
    tree: dict
    atoms: dict
    temporal: dict | None
    request: dict
    source_scope: tuple[str,...]=()
    owner_frame_ref: str | None=None


@dataclass(frozen=True)
class Pattern:
    operator: str | None=None
    members: tuple=()
    template_ref: str | None=None
    actants: tuple=()
    lexical_anchor: str | None=None
    temporal: dict | None=None


@dataclass(frozen=True)
class QueryVar:
    name: str
    sort: VariableSort=VariableSort.UNKNOWN


def project_native_queries(state,release):
    """Project validated syntax, with explicit intent supplied by host or rules."""
    evidence={e.token_id:e for e in state.evidence}; atoms={}; trees=list(state.logical_roots)
    frames={f.frame_id:f for f in state.frames}
    embedded=set()
    def leaves(t):
        if 'frame_ref' in t: return {t['frame_ref']}
        return set().union(*(leaves(c) for c in t.get('operands',())))
    for f in state.frames:
        for tree in f.semantic.get('operator_forest',()):
            if tree not in trees: trees.append(tree)
        for child in f.semantic.get('proposition_args',{}).values():
            embedded.update(leaves(child.get('tree') or {'frame_ref':child['frame_ref']}))
        d=state.decisions.get(f.frame_id+'|predicate_value')
        if any(t in state.observation.get('unresolved_references',()) for t in f.argument_token_refs):
            state.diag('QUERY_ENTITY_UNBOUND',f.frame_id); continue
        if f.semantic.get('structural_unresolved') or f.semantic.get('temporal_unresolved') or not d or d.outcome!='RESOLVED' or len(d.selected)!=1:
            continue
        selected=f.semantic['candidate_specs'][d.selected[0]]
        roles=[]
        for token,role in selected['roles'].items():
            if token in f.semantic.get('bound_arguments',{}): value={'bound_var':f.semantic['bound_arguments'][token],'sort':'ENTITY'}
            else:
                unit=f.semantic.get('lexical_units',{}).get(token,{})
                value={'mention':unit.get('surface',evidence[token].span),'entity_ref':state.observation.get('entity_bindings',{}).get(unit.get('mention_ref',token))}
            roles.append((role,value))
        for role,child in f.semantic.get('proposition_args',{}).items():
            roles.append((role,{'proposition':child.get('tree') or {'frame_ref':child['frame_ref']}}))
        request=f.semantic.get('query_request',{})
        all_roles={r for r,v in roles}|set(request.get('requested_roles',()))|({request['count_role']} if request.get('count_role') else set())
        mapping=[m for m in release.entries('TemplateMap') if m['sense_id']==selected.get('sense_id') and set(m.get('roles',()))==all_roles]
        atoms[f.frame_id]={'template_ref':mapping[0]['template_ref'] if len(mapping)==1 else None,
            'roles':roles,'temporal':f.semantic.get('region'),'lexical_anchor':f.semantic.get('lexical_units',{}).get(f.predicate_token_ref,{}).get('surface',evidence[f.predicate_token_ref].span).casefold() if selected['sense_kind']=='OPEN_LEXICAL' else None}
    structural=set().union(*(leaves(t) for t in trees))
    for f in state.frames:
        if f.frame_id in structural or f.frame_id in embedded: continue
        tree={'frame_ref':f.frame_id}
        local=state.text[slice(*f.source_range)]
        if any(r.get('operator')=='NOT' and re.search(r['pattern'],local,re.I) for r in release.entries('ScopeLexicon')):
            tree={'operator':'NOT','operands':[tree]}
        trees.append(tree)
    out=[]
    for tree in trees:
        refs=leaves(tree); fs=[frames[f] for f in refs]
        if refs&embedded or any(f.semantic.get('quoted') for f in fs): continue
        positions=[evidence[f.predicate_token_ref].start for f in fs] or [evidence[a].start for a in tree.get('anchor_refs',())]
        query=state.observation.get('request_kind')=='QUERY' or any(f.semantic.get('query_request') for f in fs)
        if state.observation.get('request_kind') in {'COMMAND','UNKNOWN','STATEMENT'}: continue
        for pos in positions:
            ends=[state.text.find(c,pos) for c in '.!?;' if state.text.find(c,pos)>=0]
            hi=min(ends) if ends else len(state.text)
            query |= hi<len(state.text) and state.text[hi]=='?'
        if not query: continue
        temporal=[f.semantic.get('region') for f in fs if f.semantic.get('region')]
        owners={f.semantic.get('time_scope_owner') for f in fs if 'time_scope_owner' in f.semantic}
        common=tree.get('region') or (temporal[0] if temporal and len({digest(t) for t in temporal})==1 and len(owners)<=1 else None)
        # Intent fields are typed host input. Surface recognition belongs to
        # released syntax/interrogative rules, never to word-specific handlers.
        request_owners=[f for f in fs if f.semantic.get('query_request')]
        requests=[f.semantic['query_request'] for f in request_owners]
        request=dict(state.observation.get('goal_request') or (requests[0] if len(requests)==1 else {}))
        if len(requests)>1:
            state.diag('QUERY_TARGET_UNBOUND','interrogative gaps need a unique owner'); continue
        owner=request_owners[0].frame_id if request_owners else fs[0].frame_id if len(fs)==1 else None
        out.append(NativeQueryRoot(tree,atoms,common,request,tuple(state.observation.get('query_source_scope',())),owner))
    return tuple(out)


def compile_native_queries(core,roots,context,attention_refs=()):
    from ah.inference.query_builder import QueryBuildResult
    from ah.integration.entity_resolver import EntityResolver,ExistingEntity
    from ah.perception.contracts import ActantCandidate
    results=[]
    for root in roots:
        try:
            request=root.request; mode=request.get('mode','FORMULA')
            gaps=tuple(request.get('requested_roles',())) if mode=='WH' else (request['count_role'],) if mode=='COUNT' else ()
            if mode in {'WH','COUNT'} and (not gaps or len(set(gaps))!=len(gaps) or root.owner_frame_ref is None):
                raise ValueError('QUERY_TARGET_UNBOUND')
            visited=set()
            def compile_tree(tree,depth=0):
                if depth>32: raise ValueError('COMPUTATION_LIMIT')
                if 'time_literal' in tree: return TimeLiteral(tuple(tree['time_literal']))
                if 'count_literal' in tree: return CountLiteral(tree['count_literal'])
                if 'bound_var' in tree: return BoundVar(tree['bound_var'],VariableSort(tree.get('sort','ENTITY')))
                if 'frame_ref' not in tree:
                    operator=core.function_registry.canonical_id(tree['operator'])
                    return Pattern(operator,tuple(compile_tree(c,depth+1) for c in tree['operands']),temporal=tree.get('region'))
                fid=tree['frame_ref']
                if fid in visited: raise ValueError('CYCLIC_PROPOSITION_ARGUMENT')
                if fid not in root.atoms: raise ValueError('QUERY_TARGET_UNBOUND')
                visited.add(fid); atom=root.atoms[fid]; actants=[]
                if not atom['lexical_anchor'] and (not atom['template_ref'] or not core.store.has_uid(atom['template_ref'])):
                    raise ValueError('CANONICAL_MAPPING_MISSING')
                for role,value in atom['roles']:
                    if 'bound_var' in value: resolved=BoundVar(value['bound_var'],VariableSort(value.get('sort','ENTITY')))
                    elif 'proposition' in value: resolved=compile_tree(value['proposition'],depth+1)
                    else:
                        if value.get('entity_ref'):
                            resolved=core.ref(value['entity_ref'])
                            if resolved.kind is not RefKind.M: raise ValueError('IDENTITY_CONFLICT')
                        else:
                            candidate=ActantCandidate(ActantRole(role),mention=value['mention'])
                            r=EntityResolver(core).resolve(candidate,context,first_person_ref=context.user_ref,
                                    second_person_ref=context.self_ref,attention_refs=attention_refs)
                            if not isinstance(r,ExistingEntity): raise ValueError('QUERY_ENTITY_UNBOUND:'+role)
                            resolved=r.ref
                    actants.append((ActantRole(role),resolved))
                if fid==root.owner_frame_ref:
                    if set(gaps)&{r.value for r,v in actants}: raise ValueError('QUERY_REQUEST_INVALID')
                    if gaps and (not atom['template_ref'] or not set(gaps)<=set(r.value for r in core.store.get_template(atom['template_ref']).roles)):
                        raise ValueError('QUERY_REQUEST_INVALID')
                    actants.extend((ActantRole(role),QueryVar(role,VariableSort.ENTITY if mode=='COUNT' else VariableSort.UNKNOWN)) for role in gaps)
                visited.remove(fid)
                if len({r for r,v in actants})!=len(actants): raise ValueError('QUERY_ARGUMENT_GROUP_UNBOUND')
                return Pattern(template_ref=atom['template_ref'],actants=tuple(actants),lexical_anchor=atom['lexical_anchor'],temporal=atom['temporal'])
            pattern=compile_tree(root.tree)
            temporal=normalize(region(root.temporal)); point=temporal.point if temporal.kind=='POINT' else None
            window=(temporal.lo,temporal.hi) if temporal.kind in {'EXISTENTIAL','CONTINUOUS'} else None
            if not set(request)<={'mode','requested_roles','count_role','expected_count','comparison','domain_certificate'}:
                raise ValueError('QUERY_REQUEST_INVALID')
            if len(root.source_scope)>16 or any(not isinstance(s,str) or not s for s in root.source_scope):
                raise ValueError('QUERY_SOURCE_SCOPE_INVALID')
            target=NativeFormulaGoal(pattern,point,window,tuple(attention_refs),root.source_scope)
            if mode in {'WH','COUNT'}:
                release=getattr(getattr(core,'_formalizer_adapter',None),'resource_release',None)
                if not pattern.operator and not pattern.lexical_anchor and all(isinstance(v,(Ref,QueryVar)) for r,v in pattern.actants):
                    tref=core.ref(pattern.template_ref); known={r:v for r,v in pattern.actants if isinstance(v,Ref)}
                    if mode=='WH':
                        roles=tuple(ActantRole(r) for r in gaps)
                        target=RoleFillGoal(tref,known,roles[0],point,window) if len(roles)==1 else MultiRoleFillGoal(tref,known,roles,point,window)
                    else:
                        target=CountGoal(tref,known,ActantRole(request['count_role']),point,window,request.get('expected_count'),request.get('comparison','EXACTLY_N'),request.get('domain_certificate'),release.sha256 if release is not None else None)
                else:
                    target=NativeBindingGoal(pattern,gaps,mode,point,window,tuple(attention_refs),root.source_scope,
                        request.get('expected_count'),request.get('comparison','EXACTLY_N'),request.get('domain_certificate'),release.sha256 if release is not None else None)
            elif mode!='FORMULA': raise ValueError('QUERY_TARGET_UNBOUND')
            if pattern.operator=='COUNTERFACTUAL':
                # Legacy proof does not filter native derived paths by temporary
                # assumptions. A world answer is not a counterfactual proof.
                raise ValueError('COUNTERFACTUAL_NATIVE_SCOPE_NOT_IMPLEMENTED')
            if pattern.operator=='ASSOCIATION':
                adapter=getattr(core,'_formalizer_adapter',None)
                if adapter is None: raise ValueError('QUERY_TARGET_UNBOUND')
                with adapter._journal.atomic(),core.store._lock:
                    adapter._refresh()
                    refs=[_matching_refs(core,adapter.ledger,p,limit=1024) for p in pattern.members]
                if len(refs)!=2 or any(len(rs)!=1 for rs in refs): raise ValueError('QUERY_TARGET_UNBOUND')
                target=AssociationGoal(core.ref(refs[0][0]),core.ref(refs[1][0]))
            results.append(QueryBuildResult(InferenceQuery(GoalSpec(target)),('NATIVE_GOAL_COMPILED',),tuple(attention_refs)))
        except (KeyError,ValueError,TypeError) as exc:
            results.append(QueryBuildResult(None,(str(exc),'QUERY_TARGET_UNBOUND')))
    return tuple(results)


def _matching_refs(core,ledger,pattern,*,limit,workspace=()):
    """Narrow leaf T lookup then reverse function index, with bounded unification."""
    steps=0
    workspace_ids={r.uid for r in workspace}
    def walk(p):
        if not isinstance(p,Pattern): return []
        if p.operator is None:
            if p.lexical_anchor:
                # Exact attestation is restricted to the already excited workspace.
                return [uid for uid in sorted(workspace_ids) if uid in ledger.data['nodes'] and match(p,uid,{})]
            return [n.uid for n in core.store.find_hypernodes_by_template(p.template_ref) if match(p,n.uid,{})]
        seed=next((m for m in p.members if isinstance(m,Pattern)),None)
        if seed is None:
            # Literal temporal formulas have no Ref edge to index; exact G UID
            # is computable from the same typed operands as C, without a scan.
            from .canonical_ledger import digest
            if not all(isinstance(m,TimeLiteral) for m in p.members): return []
            uid='G:'+digest([p.operator,[{'time_literal':list(m.bounds)} for m in p.members]])
            return [uid] if uid in ledger.data['nodes'] else []
        parents=set()
        for uid in walk(seed):
            for g in core.store.function_parents(uid):
                steps_used[0]+=1
                if steps_used[0]>limit: raise ValueError('COMPUTATION_LIMIT')
                parents.add(g.uid)
        return [uid for uid in sorted(parents) if match(p,uid,{})]
    def match(p,uid,variables):
        nonlocal steps
        steps+=1
        if steps>limit: raise ValueError('COMPUTATION_LIMIT')
        node=ledger.data['nodes'].get(uid)
        if node is None: return False
        if p.operator is not None:
            if node.get('function_id')!=p.operator or len(node.get('operands',()))!=len(p.members): return False
            actual=list(node['operands'])
            if p.operator in {'AND','OR','XOR'}:
                # Match a multiset, not a syntactic permutation. Every pairing
                # retains its own alpha-variable environment.
                def pair(members,remaining,env):
                    nonlocal steps
                    steps+=1
                    if steps>limit: raise ValueError('COMPUTATION_LIMIT')
                    if not members: variables.update(env); return True
                    for i,value in enumerate(remaining):
                        local=dict(env)
                        if operand(members[0],value,local) and pair(members[1:],remaining[:i]+remaining[i+1:],local): return True
                    return False
                return pair(list(p.members),actual,dict(variables))
            return all(operand(a,b,variables) for a,b in zip(p.members,actual))
        if node.get('function_id'): return False
        if p.lexical_anchor:
            if node.get('semantic_status')!='UNLINKED' or uid not in workspace_ids: return False
            template=core.store.get_template(node['template_ref'])
            if p.lexical_anchor not in {s.casefold() for s in core.store.get_symbol(template.predicate.uid).forms}: return False
        elif node.get('template_ref')!=p.template_ref: return False
        actual=node.get('actants',{})
        if set(actual)!={r.value for r,v in p.actants}: return False
        return all(operand(value,actual[role.value],variables) for role,value in p.actants)
    def operand(p,value,variables):
        if isinstance(p,Pattern): return isinstance(value,str) and match(p,value,variables)
        if isinstance(p,Ref): return value==p.uid
        if isinstance(p,TimeLiteral): return isinstance(value,dict) and tuple(value.get('time_literal',()))==p.bounds
        if isinstance(p,CountLiteral): return isinstance(value,dict) and value.get('count_literal')==p.value
        if isinstance(p,BoundVar):
            if not isinstance(value,dict) or 'bound_var' not in value: return False
            old=variables.setdefault(p.local_id,value['bound_var'])
            return old==value['bound_var'] and value.get('sort','ENTITY')==p.sort.value and len(set(variables.values()))==len(variables)
        return False
    steps_used=[0]
    return walk(pattern)


def solve_native_goal(engine,goal,query,workspace,attention,context,runtime,*,_budget=None,_depth=0):
    adapter=getattr(engine.core,'_formalizer_adapter',None)
    def outcome(status,refs=(),diagnostics=(),conclusion=None):
        if runtime is not None:
            for ref in refs: runtime.focus(ref,logical_depth=_depth,reason='native query proof premise')
            if status is not LogicalStatus.UNKNOWN:
                runtime.rule('NATIVE_QUERY',logical_depth=_depth,detail='status='+status.value)
        stop=StopReason.GOAL_SATISFIED if status is LogicalStatus.PROVED else StopReason.GOAL_REFUTED if status is LogicalStatus.DISPROVED else StopReason.SEARCH_EXHAUSTED
        return InferenceOutcome(status,stop,conclusion or (ExistingRefConclusion(refs[0]) if refs else None),tuple(refs),tuple(refs),None,len(refs)+1,tuple(diagnostics),proof_support=(ProofSupport(tuple(refs),rule_id='NATIVE_FACT_MATCH'),) if refs else ())
    if adapter is None: return outcome(LogicalStatus.UNKNOWN,diagnostics=('NATIVE_STORE_REQUIRED',))
    if _budget is None:
        _budget=[query.max_expanded_states if query.max_expanded_states is not None else engine.settings.max_expanded_states]
    _budget[0]-=1
    if _budget[0]<0 or _depth>(query.max_depth if query.max_depth is not None else engine.settings.max_depth):
        return outcome(LogicalStatus.UNKNOWN,diagnostics=('COMPUTATION_LIMIT',))
    with adapter._journal.atomic(),engine.core.store._lock:
        adapter._refresh(); ledger=adapter.ledger
        try:
            if isinstance(goal,NativeBindingGoal):
                from .query_bindings import solve_bindings
                return solve_bindings(engine,adapter,goal,query,workspace,attention,context,runtime,_budget,_depth,outcome)
            if isinstance(goal,CountGoal):
                witnesses={}; scanned=0
                if runtime is not None:
                    runtime.focus(goal.template_ref,logical_depth=_depth,reason='count template seed')
                    runtime.memory_query('COUNT_WITNESSES',goal.template_ref.uid,logical_depth=_depth,detail='distinct live entity witnesses; scoped completeness only')
                if not (set(goal.known_roles)|{goal.count_role})<=set(engine.core.store.get_template(goal.template_ref.uid).roles): raise ValueError('QUERY_REQUEST_INVALID')
                for node in engine.core.store.find_hypernodes_by_template(goal.template_ref.uid):
                    scanned+=1
                    _budget[0]-=1
                    if scanned>1024 or _budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
                    spec=ledger.data['nodes'].get(node.uid,{})
                    actual=spec.get('actants',{})
                    if any(actual.get(r.value)!=v.uid for r,v in goal.known_roles.items()): continue
                    if ledger.query(node.uid,point=goal.temporal_point,window=goal.temporal_window)['answer']!='YES': continue
                    value=actual.get(goal.count_role.value)
                    if isinstance(value,str) and engine.core.store.kind_of(value) is RefKind.M: witnesses.setdefault(value,engine.core.ref(node.uid))
                claimed_lower,claimed_upper,bound_refs=_numeric_bounds(engine.core,ledger,goal,_budget)
                lower=max(len(witnesses),claimed_lower or 0)
                certificate=_complete_domain(adapter,ledger,goal)
                certificate_supports=certificate['completeness_evidence'] if certificate else ()
                complete=bool(certificate_supports)
                if complete and certificate.get('closure_mode','ENUMERATED')=='ASSERTED_BOUND':
                    complete=claimed_lower is not None and claimed_lower==claimed_upper
                status=LogicalStatus.UNKNOWN
                exact=(claimed_lower if certificate.get('closure_mode','ENUMERATED')=='ASSERTED_BOUND' else len(witnesses)) if complete else None
                if complete and (lower>exact or claimed_upper is not None and exact>claimed_upper):
                    return outcome(LogicalStatus.UNKNOWN,(*witnesses.values(),*bound_refs),('COUNT_BOUNDS_CONFLICT',),CountConclusion(lower,None,tuple(witnesses.values()),claimed_upper))
                if claimed_upper is not None and lower>claimed_upper:
                    return outcome(LogicalStatus.UNKNOWN,(*witnesses.values(),*bound_refs),('COUNT_BOUNDS_CONFLICT',),CountConclusion(lower,None,tuple(witnesses.values()),claimed_upper))
                if complete:
                    valid=goal.expected_count is None or (exact==goal.expected_count if goal.comparison=='EXACTLY_N' else exact>=goal.expected_count if goal.comparison=='AT_LEAST_N' else exact<=goal.expected_count)
                    status=LogicalStatus.PROVED if valid else LogicalStatus.DISPROVED
                elif goal.expected_count is not None:
                    if goal.comparison=='AT_LEAST_N' and lower>=goal.expected_count: status=LogicalStatus.PROVED
                    elif goal.comparison in {'AT_MOST_N','EXACTLY_N'} and lower>goal.expected_count: status=LogicalStatus.DISPROVED
                proof_refs=tuple(dict.fromkeys([*witnesses.values(),*bound_refs,*(engine.core.ref(ledger.data['supports'][sid]['conclusion_ref']) for sid in certificate_supports)]))
                return outcome(status,proof_refs,() if complete else ('INCOMPLETE_DOMAIN',),CountConclusion(lower if lower else claimed_lower,exact,tuple(witnesses.values()),exact if complete else claimed_upper))
            pattern=goal.pattern
            if not isinstance(pattern,Pattern) or len(pattern.members)>128: raise ValueError('QUERY_TARGET_UNBOUND')
            if pattern.temporal is not None:
                own=normalize(region(pattern.temporal))
                goal=replace(goal,temporal_point=own.point if own.kind=='POINT' else None,
                             temporal_window=(own.lo,own.hi) if own.kind in {'CONTINUOUS','EXISTENTIAL'} else None)
            if pattern.operator in {'BEFORE','AFTER','DURING'} and all(isinstance(p,TimeLiteral) for p in pattern.members):
                from .temporal_order import compare_anchors
                value=compare_anchors(pattern.operator,*pattern.members)
                return outcome(LogicalStatus.UNKNOWN if value is None else LogicalStatus.PROVED if value else LogicalStatus.DISPROVED,
                               diagnostics=('TEMPORAL_ANCHOR_COMPARISON',),
                               conclusion=TemporalComparisonConclusion(pattern.operator,pattern.members[0].bounds,pattern.members[1].bounds) if value is not None else None)
            if pattern.operator is None and not pattern.lexical_anchor and all(isinstance(v,Ref) for r,v in pattern.actants):
                atom=ExistsGoal(engine.core.ref(pattern.template_ref),dict(pattern.actants),goal.temporal_point,goal.temporal_window)
                return engine._solve_goal(atom,query,workspace,attention,proof_context=context,runtime=runtime)
            scoped=[]
            if goal.source_scope:
                paths=ledger.paths()
                for i,(sid,s) in enumerate(ledger.data['supports'].items()):
                    if i>=10000: raise ValueError('COMPUTATION_LIMIT')
                    if sid in paths and s.get('source_tag',[None])[0] in goal.source_scope:
                        scoped.append(engine.core.ref(s['conclusion_ref']))
            refs=_matching_refs(engine.core,ledger,pattern,limit=4096,workspace=(*workspace,*goal.workspace_refs,*scoped))
            if runtime is not None:
                runtime.memory_query('NATIVE_FORMULA',pattern.operator or pattern.template_ref or pattern.lexical_anchor,logical_depth=_depth,candidate_count=len(refs),detail='template/reverse-function index or declared attestation workspace')
            conflicts=set()
            for uid in refs:
                if not _uniform_windows(pattern,goal): continue
                answer=ledger.query_proposition(uid,point=goal.temporal_point,window=goal.temporal_window)
                conflicts.update(answer['conflict_ref'])
                if answer['answer'] in {'YES','NO'}:
                    return outcome(LogicalStatus.PROVED if answer['answer']=='YES' else LogicalStatus.DISPROVED,(engine.core.ref(answer.get('evidence_ref',uid)),),tuple('conflict_ref:'+r for r in sorted(conflicts)))
            if pattern.operator in {'BEFORE','AFTER','DURING'}:
                from .temporal_order import prove_order
                result=prove_order(engine.core,ledger,pattern,goal,_budget,(*workspace,*goal.workspace_refs,*scoped))
                if result is not None:
                    value,premises=result
                    return outcome(LogicalStatus.PROVED if value else LogicalStatus.DISPROVED,premises,
                                   ('TEMPORAL_EVIDENCE_ORDER',),FormulaQueryConclusion(pattern.operator,premises))
            if pattern.operator=='EXISTS' and len(pattern.members)==2 and isinstance(pattern.members[0],BoundVar):
                witness=_existential_witness(engine,adapter,pattern.members[0],pattern.members[1],goal,query,workspace,attention,context,runtime,_budget,_depth)
                if witness is not None: return witness
            # Negation is proof inversion, never absence-as-negative. The child
            # is a typed query, so its own open-world/time contract remains intact.
            if pattern.operator=='NOT':
                child=replace(goal,pattern=pattern.members[0])
                answer=solve_native_goal(engine,child,query,workspace,attention,context,runtime,_budget=_budget,_depth=_depth+1)
                if answer.status is not LogicalStatus.UNKNOWN:
                    status=LogicalStatus.DISPROVED if answer.status is LogicalStatus.PROVED else LogicalStatus.PROVED
                    return replace(answer,status=status,stop_reason=StopReason.GOAL_SATISFIED if status is LogicalStatus.PROVED else StopReason.GOAL_REFUTED)
            if pattern.operator in {'AND','OR','XOR'}:
                children=[solve_native_goal(engine,replace(goal,pattern=p),query,workspace,attention,context,runtime,_budget=_budget,_depth=_depth+1) for p in pattern.members]
                yes=[c for c in children if c.status is LogicalStatus.PROVED]
                no=[c for c in children if c.status is LogicalStatus.DISPROVED]
                status=LogicalStatus.UNKNOWN
                if pattern.operator=='AND':
                    if no: status=LogicalStatus.DISPROVED
                    elif len(yes)==len(children):
                        if goal.temporal_point is None and goal.temporal_window is None or _joint_witness(adapter.ledger,children,goal):
                            status=LogicalStatus.PROVED
                elif pattern.operator=='OR':
                    if yes: status=LogicalStatus.PROVED
                    elif len(no)==len(children): status=LogicalStatus.DISPROVED
                else:
                    if len(yes)>1 or len(no)==len(children): status=LogicalStatus.DISPROVED
                    elif len(yes)==1 and len(no)==len(children)-1: status=LogicalStatus.PROVED
                if status is not LogicalStatus.UNKNOWN:
                    premises=tuple(dict.fromkeys(r for c in children for r in c.premise_refs))
                    diagnostics=tuple(dict.fromkeys(d for c in children for d in c.diagnostics))
                    return outcome(status,premises,diagnostics,FormulaQueryConclusion(pattern.operator,premises))
            return outcome(LogicalStatus.UNKNOWN,diagnostics=tuple('conflict_ref:'+r for r in sorted(conflicts)))
        except (ValueError,KeyError,TypeError) as exc:
            return outcome(LogicalStatus.UNKNOWN,diagnostics=(str(exc),))


def _numeric_bounds(core,ledger,goal,budget):
    """Read only asserted cardinality scopes matching the complete atomic body.

    A conjunction/restriction is never dropped to make a count claim match.
    More complex bodies are matched as formula goals, not broadened here.
    """
    lower=None; upper=None; proofs=[]
    for body in core.store.find_hypernodes_by_template(goal.template_ref.uid):
        budget[0]-=1
        if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
        spec=ledger.data['nodes'].get(body.uid,{})
        actual=spec.get('actants',{})
        variable=actual.get(goal.count_role.value)
        if not isinstance(variable,dict) or 'bound_var' not in variable: continue
        if set(actual)!={*(r.value for r in goal.known_roles),goal.count_role.value}: continue
        if any(actual.get(r.value)!=v.uid for r,v in goal.known_roles.items()): continue
        for root in core.store.function_parents(body.uid):
            budget[0]-=1
            if budget[0]<0: raise ValueError('COMPUTATION_LIMIT')
            claim=ledger.data['nodes'].get(root.uid,{})
            kind=claim.get('function_id'); operands=claim.get('operands',())
            if kind not in {'AT_LEAST_N','EXACTLY_N','AT_MOST_N'} or len(operands)!=3 or operands[0]!=variable or operands[1]!=body.uid: continue
            # A count that holds at one unknown instant in Q does not bound
            # distinct witnesses across Q. Aggregated window domains require
            # an explicit CountDomain contract; never reinterpret TimeAssertion.
            if goal.temporal_window is not None: continue
            if goal.temporal_point is None:
                paths=ledger.paths()
                if not any(s['conclusion_ref']==root.uid and sid in paths
                           and not any(a['support_record_id']==sid for a in ledger.data['assertions'].values())
                           for sid,s in ledger.data['supports'].items()): continue
            if ledger.query(root.uid,point=goal.temporal_point,window=goal.temporal_window)['answer']!='YES': continue
            value=operands[2].get('count_literal') if isinstance(operands[2],dict) else None
            if type(value) is not int or value<0: raise ValueError('INTEGRITY_ERROR: invalid count scope')
            if kind in {'AT_LEAST_N','EXACTLY_N'}: lower=value if lower is None else max(lower,value)
            if kind in {'AT_MOST_N','EXACTLY_N'}: upper=value if upper is None else min(upper,value)
            proofs.append(core.ref(root.uid))
    return lower,upper,tuple(dict.fromkeys(proofs))


def _complete_domain(adapter,ledger,goal):
    """A released certificate names its exact count scope and live truth sources.

    The query may select a domain_id, never declare completeness. A changed
    resource snapshot or a retracted certificate source opens the domain again.
    """
    if goal.domain_certificate is not None and (not isinstance(goal.domain_certificate,str) or not goal.domain_certificate):
        raise ValueError('DOMAIN_CERTIFICATE_INVALID')
    release=getattr(adapter,'resource_release',None)
    if release is None or goal.resource_snapshot!=release.sha256: return None
    release.assert_integrity()
    window=([goal.temporal_point,goal.temporal_point] if goal.temporal_point is not None
            else list(goal.temporal_window) if goal.temporal_window is not None else None)
    certs=[c for c in release.resources.get('DomainCertificate',{}).get('entries',())
           if (goal.domain_certificate is None or c['domain_id']==goal.domain_certificate)
           and c['template_ref']==goal.template_ref.uid and c['count_role']==goal.count_role.value
           and c['known_roles']=={r.value:v.uid for r,v in goal.known_roles.items()}
           and c['request_window']==window]
    paths=ledger.paths()
    for c in sorted(certs,key=lambda c:c['domain_id']):
        if all(sid in paths for sid in c['completeness_evidence']): return c
    return None


def _existential_witness(engine,adapter,variable,body,goal,query,workspace,attention,context,runtime,budget,depth):
    """Bind a candidate then prove the entire nested body; absence is UNKNOWN."""
    from .query_bindings import candidate_values,substitute
    if variable.sort not in {VariableSort.ENTITY,VariableSort.UNKNOWN}: return None
    values=candidate_values(engine.core,adapter.ledger,body,(variable.local_id,),budget,bound=True)[variable.local_id]
    for uid in sorted(values):
        ground=substitute(body,{variable.local_id:engine.core.ref(uid)},bound=True)
        answer=solve_native_goal(engine,replace(goal,pattern=ground),query,workspace,attention,context,runtime,_budget=budget,_depth=depth+1)
        if 'COMPUTATION_LIMIT' in answer.diagnostics: raise ValueError('COMPUTATION_LIMIT')
        if answer.status is LogicalStatus.PROVED:
            refs=answer.premise_refs
            if runtime is not None: runtime.rule('EXISTS_WITNESS',logical_depth=depth,detail='one shared entity binding; full body proved')
            return InferenceOutcome(LogicalStatus.PROVED,StopReason.GOAL_SATISFIED,
                FormulaQueryConclusion('EXISTS',refs),refs,refs,None,answer.expanded_states+1,
                answer.diagnostics,proof_support=(ProofSupport(refs,rule_id='EXISTS_WITNESS'),))
    return None


def _joint_witness(ledger,children,goal):
    """Never turn independent existential windows into one simultaneous AND."""
    options=[]
    for child in children:
        if not isinstance(child.conclusion,ExistingRefConclusion): return False
        uid=child.conclusion.ref.uid
        evidence=[a for aid,a in ledger.data['assertions'].items()
                  if a['target_ref']==uid and ledger.evidence_live({'record_id':aid})]
        if not evidence: return False
        options.append(evidence)
    for i,combo in enumerate(islice(product(*options),65)):
        if i==64: raise ValueError('COMPUTATION_LIMIT')
        regions=[normalize(region(a['region'])) for a in combo]
        witness=combo[0].get('witness_ref')
        if witness and all(a.get('witness_ref')==witness and a['region']==combo[0]['region'] for a in combo):
            if _answers_window(regions[0],goal): return True
        points=[r.point for r in regions if r.kind=='POINT']
        continuous=[r for r in regions if r.kind=='CONTINUOUS']
        existential=[r for r in regions if r.kind=='EXISTENTIAL']
        if points:
            if len(set(points))!=1 or existential: continue
            p=TemporalRegion('POINT',point=points[0])
            if all(covers(r,p) is True for r in continuous) and _answers_window(p,goal): return True
        elif continuous:
            if any(r.lo is None or r.hi is None for r in continuous): continue
            lo=max(r.lo for r in continuous); hi=min(r.hi for r in continuous)
            if lo>hi: continue
            common=TemporalRegion('CONTINUOUS',lo=lo,hi=hi)
            if not existential and _answers_window(common,goal): return True
            if len(existential)==1 and covers(common,existential[0]) is True and _answers_window(existential[0],goal): return True
    return False


def _uniform_windows(pattern,goal):
    """An undated wrapper cannot certify differently dated query operands."""
    effective=(goal.temporal_point,goal.temporal_window)
    def walk(p):
        if not isinstance(p,Pattern): return True
        if p.temporal:
            t=normalize(region(p.temporal))
            local=(t.point if t.kind=='POINT' else None,(t.lo,t.hi) if t.kind in {'CONTINUOUS','EXISTENTIAL'} else None)
            if local!=effective: return False
        return all(walk(c) for c in p.members) and all(walk(v) for r,v in p.actants)
    return walk(pattern)


def _answers_window(r,goal):
    if goal.temporal_point is not None:
        return covers(r,TemporalRegion('POINT',point=goal.temporal_point)) is True
    if goal.temporal_window is None: return True
    lo,hi=goal.temporal_window
    return (r.kind=='POINT' and lo<=r.point<=hi or
            r.kind=='CONTINUOUS' and r.lo is not None and r.hi is not None and max(lo,r.lo)<=min(hi,r.hi) or
            r.kind=='EXISTENTIAL' and covers(TemporalRegion('CONTINUOUS',lo=lo,hi=hi),r) is True)
