"""Local scope assignment with shared children, before lexical materialization.

The same operation inserts a modifier at a slot of a single event or a
coordinated tree. Alternatives differ in one edge; no permutations of bundles.
"""
from copy import deepcopy
from .canonical_ledger import digest
from .composition_tree import reference
from .component_probe import _probe


def expanded_leaves(tree,contents,seen=frozenset()):
    fid=tree.get('frame_ref')
    if fid is not None:
        if fid in seen:raise ValueError('COMPOSITION_CYCLE')
        return {fid}|(expanded_leaves(contents[fid],contents,seen|{fid}) if fid in contents else set())
    return set().union(*(expanded_leaves(c,contents,seen) for c in tree.get('operands',())))


def positions(tree, contents, path=(), active=frozenset()):
    # Bound variables, time literals and counts are typed values, not slots
    # where a proposition modifier/operator may be inserted.
    if 'frame_ref' not in tree and 'operator' not in tree:return
    yield path, tree
    if 'frame_ref' in tree and tree['frame_ref'] in contents:
        fid = tree['frame_ref']
        if fid in active:
            raise ValueError('COMPOSITION_CYCLE')
        yield from positions(contents[fid], contents, (*path, ('content', fid)), active | {fid})
    else:
        children=tree.get('operands',())
        # A flat n-ary coordinate node may acquire an immediate subgroup.
        # Propose one interval edge, never full combinations of groupings.
        if tree.get('operator')=='AND' and len(children)>2:
            for start in range(len(children)):
                for end in range(start+2,len(children)+1):
                    if start==0 and end==len(children):continue
                    yield (*path,('group',(start,end))),{'operator':'AND','operands':list(children[start:end])}
        for index, child in enumerate(tree.get('operands', ())):
            yield from positions(child, contents, (*path, ('operand', index)), active)


def replace(tree, contents, path, replacement):
    """Persistent expression update; lexical child identity is preserved."""
    if not path:
        return deepcopy(replacement)
    (kind, key), *tail = path
    if kind == 'content':
        contents[key] = replace(contents[key], contents, tail, replacement)
        return tree
    result = dict(tree)
    result['operands'] = list(tree['operands'])
    if kind=='group':
        if tail:raise ValueError('COMPOSITION_GROUP_PATH_INVALID')
        start,end=key
        result['operands'][start:end]=[deepcopy(replacement)]
        return result
    result['operands'][key] = replace(result['operands'][key], contents, tail, replacement)
    return result


def assign(state, release, selector, region, tree, modifiers, cfg, *, contents=None, node_labels=None):
    from .syntax_rules import SearchLimit
    remaining=release.entries('ProposalPolicy')[0].get('max_rule_steps',20000)
    def spend():
        nonlocal remaining
        remaining-=1
        if remaining<0:raise SearchLimit('COMPOSITION_SCOPE_SEARCH_INCOMPLETE')
    try:
        return _assign(state,release,selector,region,tree,modifiers,cfg,contents=contents,
                       node_labels=node_labels,spend=spend)
    except SearchLimit as exc:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',str(exc));return None


def _assign(state, release, selector, region, tree, modifiers, cfg, *, contents=None, node_labels=None,spend):
    """Joint immediate-content domains, including not-yet-assembled peers.

    Each edge names an immutable base slot and optionally another modifier.
    Whole topology permutations are never enumerated. Pair constraints and
    forced-cycle propagation run before each closed local question.
    """
    from .composition_domains import DomainNetwork
    contents=deepcopy(contents or {});tree=deepcopy(tree)
    labels={**(node_labels or {}),**{m['id']:m['label'] for m in modifiers}}
    by_id={m['id']:m for m in modifiers}
    bases=dict(positions(tree,contents));decisions=[]
    def describe(node):
        if 'frame_ref' in node:
            fid=node['frame_ref']
            return labels.get(fid,fid)+('('+describe(contents[fid])+')' if fid in contents else '')
        if 'bound_var' in node:return 'variable '+str(node['bound_var'])
        return node.get('operator','value')+'('+', '.join(describe(c) for c in node.get('operands',()))+')'
    def permits(modifier,path,target):
        origin=set(modifier.get('source_refs',()))
        required=set(modifier.get('required_refs',()))
        refs=expanded_leaves(target,contents)
        if required and not required<=refs:return False
        if origin and not refs&origin:return False
        if not origin and modifier.get('source_index') is not None:
            indices=[key for kind,key in path if kind=='operand']
            if indices and indices[0]!=modifier['source_index']:return False
        return modifier.get('allowed_paths') is None or path in modifier['allowed_paths']
    domains={}
    for mid,modifier in by_id.items():
        options={}
        for path,target in bases.items():
            spend()
            if not permits(modifier,path,target):continue
            targets=[None]+[other for other in by_id if other!=mid and
                not by_id[other].get('outer') and permits(by_id[other],path,target)]
            for other in targets:
                for shared in (False,True) if modifier.get('allow_shared') and (other or target.get('frame_ref') in contents) else (False,):
                    spend()
                    value={'base':path,'target':other,'shared':shared}
                    cid='scope-edge:'+digest([mid,tree,contents,value])
                    content=labels[other]+' (at '+describe(target)+')' if other else describe(target)
                    label=(modifier['label']+' independently describes the SAME content as '+content
                           if shared else modifier['label']+' applies to '+content)
                    if modifier.get('source_index') is not None and not any(k=='operand' for k,v in path):
                        label+='; SHARED scope across compatible conjuncts'
                    options[cid]={**value,'candidate_id':cid,'label':label}
        if not options or len(options)>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE' if options else 'NO_GROUNDED_CANDIDATE',region.region_id)
            return None
        domains[mid]=options
    graph=DomainNetwork(domains)
    ids=list(by_id)
    def crossing(a,b):
        if not a or not b or a[:-1]!=b[:-1] or a[-1][0]!='group' or b[-1][0]!='group':return False
        x,y=a[-1][1];u,v=b[-1][1]
        return x<u<y<v or u<x<v<y
    def compatible(left,a,right,b):
        if a['target']==right and b['target']==left:return False
        if a['target']==right or b['target']==left:
            return a['base']==b['base']
        if a['target']==b['target'] and a['base']==b['base']:return False
        if crossing(a['base'],b['base']):return False
        return True
    for i,left in enumerate(ids):
        for right in ids[i+1:]:
            graph.connect(left,right,lambda a,b,left=left,right=right:compatible(left,a,right,b),
                          'SCOPE_SINGLE_CONTENT_ACYCLIC_DOMINANCE')
    chosen={};attempted=set();round_no=0;questions={}
    while len(chosen)<len(ids):
        # Reject an edge closing a cycle through already forced edges. Unknown
        # peer edges remain live; they are not guessed or treated as facts.
        changed=True
        while changed:
            changed=False
            if not graph.propagate(spend):
                state.diag('COMPOSITION_SCOPE_CONFLICT',region.region_id);return None
            for mid,values in graph.domains.items():
                allowed=[]
                for cid,value in values.items():
                    spend()
                    seen={mid};target=value['target']
                    while target is not None and target not in seen and len(graph.domains[target])==1:
                        spend()
                        seen.add(target);target=next(iter(graph.domains[target].values()))['target']
                    if target not in seen:allowed.append(cid)
                before=len(values);graph.restrict(mid,allowed,'SCOPE_FORCED_CYCLE')
                changed |= len(graph.domains[mid])!=before
        snapshot=graph.snapshot()
        state.syntax_trace.append({'kind':'SCOPE_DOMAIN','region_ref':region.region_id,
            'round':round_no,'constraint_state':snapshot,
            **({'values':domains} if round_no==0 else {})})
        round_no+=1
        pending=[mid for mid in ids if mid not in chosen and
                 (mid,digest(snapshot['domains'])) not in attempted]
        if not pending:
            state.diag('COMPOSITION_SCOPE_UNRESOLVED',region.region_id);return None
        mid=min(pending,key=lambda item:(len(graph.domains[item]),ids.index(item)))
        options=list(graph.domains[mid].values());signature=digest(snapshot['domains'])
        attempted.add((mid,signature))
        fixed=[by_id[m]['label']+' -> '+v['label'] for m,v in chosen.items()]
        key=region.region_id+'|scope-slot:'+digest([mid,options,fixed])
        from .component_probe_replay import supersede
        supersede(state,questions.get(mid),key);questions[mid]=key
        question=('Choose the immediate content of this modifier. Other listed modifiers are retained slots, '
                  'even if their content is not selected yet. Select one local edge, not a whole tree. '
                  'Preserve variable binding, source ownership and scope barriers; no scope choice asserts occurrence. '
                  'Established edges: '+str(fixed)+'. ')
        if by_id[mid].get('source_index') is not None:
            question+=('Declared SHARED_COORDINATION_V1 preference: when compatible with every conjunct '
                       'and no contrast or scope barrier is supported, prefer shared scope. '
                       'Mere logical possibility of a local reading is not a reason to abstain. ')
        selected=_probe(state,selector,release,key,'modifier_scope',options,
                        state.text[slice(*region.source_range)],region.source_range,question=question)
        state.syntax_trace.append({'kind':'SCOPE_SLOT','decision_ref':key,'modifier_ref':mid,
                                   'alternatives':options,'selected':selected})
        if selected not in graph.domains[mid]:continue
        chosen[mid]=graph.domains[mid][selected]
        if (by_id[mid].get('source_index') is not None and not any(k=='operand' for k,v in chosen[mid]['base'])
                and key in state.decisions):
            from .state import Ground
            from dataclasses import asdict
            decision=state.decisions[key]
            decision.grounds.append(Ground('R','SHARED_COORDINATION_V1: compatible conjuncts without a supported separator',selected))
            decision.history.append({'kind':'SCOPE_PREFERENCE','rule_id':'SHARED_COORDINATION_V1',
                'selected':selected,'reason':'PREFERRED_INTERPRETATION_NOT_LOGICAL_EXCLUSION'})
            state.component_probe_records[key]['decision']=asdict(decision)
        graph.restrict(mid,[selected],'RESOLVED_SCOPE_EDGE');decisions.append(key)
    if not graph.propagate(spend):
        state.diag('COMPOSITION_SCOPE_CONFLICT',region.region_id);return None
    # At closure, each chain ends in exactly one original slot. Render from
    # original addresses so nested AND intervals never shift later indices.
    anchored={}
    for mid,value in chosen.items():anchored.setdefault(value['base'],[]).append(mid)
    def wrap(path,base):
        members=anchored.get(path,())
        if not members:return base
        targets={chosen[m]['target'] for m in members}
        roots=[m for m in members if m not in targets]
        if len(roots)!=1:raise ValueError('COMPOSITION_SCOPE_CONFLICT')
        active=set()
        def lower(mid):
            if mid in active:raise ValueError('COMPOSITION_CYCLE')
            active.add(mid);value=chosen[mid];target=value['target']
            child=lower(target) if target else deepcopy(base)
            if value['shared']:
                content=contents[target] if target else contents[base['frame_ref']]
                contents[mid]=deepcopy(content)
                result={'operator':'AND','operands':[child,reference(mid)]}
            else:
                contents[mid]=child;result=reference(mid)
            active.remove(mid);return result
        return lower(roots[0])
    def render(node,path=()):
        node=deepcopy(node)
        if 'frame_ref' in node and node['frame_ref'] in contents:
            fid=node['frame_ref'];contents[fid]=render(contents[fid],(*path,('content',fid)))
        elif 'operands' in node:
            children=[render(c,(*path,('operand',i))) for i,c in enumerate(node['operands'])]
            groups={p[-1][1]:p for p in anchored if p and p[:-1]==path and p[-1][0]=='group'}
            def interval(start,end):
                result=[];i=start
                while i<end:
                    ends=[b for a,b in groups if a==i and b<=end and (a,b)!=(start,end)]
                    if ends:
                        stop=max(ends);sub={'operator':'AND','operands':interval(i,stop)}
                        result.append(wrap(groups[i,stop],sub));i=stop
                    else:result.append(children[i]);i+=1
                return result
            node['operands']=interval(0,len(children))
        return wrap(path,node)
    try:result=render(tree)
    except ValueError as exc:
        state.diag(str(exc),region.region_id);return None
    return result,contents,decisions


def modifier_shape(tree, contents, ids, base):
    """Lower selected slots to the existing nominal materializer's shape."""
    if tree == reference(base):
        return None
    if 'frame_ref' in tree:
        fid = tree['frame_ref']
        return ('MOD', ids.index(fid), modifier_shape(contents[fid], contents, ids, base))
    return ('AND', tuple(modifier_shape(c, contents, ids, base) for c in tree['operands']))
