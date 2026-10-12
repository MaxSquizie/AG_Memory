"""Lossless local scope contrast over already generated whole candidates."""
from dataclasses import asdict
from .canonical_ledger import digest


def contrast(bundles, evidence):
    """Use short edge labels only when every non-scope field is identical.

    No semantic equivalence or commutativity is inferred. Unknown fields stay
    in the backbone comparison, so a differing one prevents this projection.
    """
    if len(bundles)<2: return None
    projections=[]; labels={}
    for bundle in bundles:
        names={f.frame_id:'node:'+f.predicate_token_ref+':'+f.semantic.get('nominal_dependency_kind','') for f in bundle}
        if len(set(names.values()))!=len(names): return None
        refs=dict(names)
        for f in bundle:
            for role,gap in f.semantic.get('implicit_arguments',{}).items():
                refs[gap['gap_id']]=names[f.frame_id]+'|gap:'+role
        def normalize(value):
            if isinstance(value,str): return refs.get(value,value)
            if isinstance(value,dict): return {refs.get(k,k):normalize(v) for k,v in value.items()}
            if isinstance(value,(list,tuple)): return [normalize(v) for v in value]
            return value
        cores={};edges={};parents={}
        labels['SOURCE']='source assertion'
        def scope(t):
            if set(t)=={'frame_ref'}:return refs[t['frame_ref']]
            if t.get('operator')!='AND' or set(t)-{'operator','operands'}:raise ValueError
            children=sorted(scope(c) for c in t['operands'])
            name='scope:'+digest(children);labels[name]='BOTH descriptions'
            for child in children:
                edge={'parent':name,'role':'AND','child':child,'attitude':'OPERATOR'}
                edges[digest(edge)]=edge
            return name
        try:
            carrier=next((f for f in bundle if f.semantic.get('component_scope_tree')),None)
            if carrier:
                edge={'parent':'SOURCE','role':'ASSERTS','child':scope(carrier.semantic['component_scope_tree']),'attitude':'ROOT'}
                edges[digest(edge)]=edge
        except (ValueError,KeyError):return None
        for f in bundle:
            name=names[f.frame_id]
            labels[name]='«'+f.anchor_span+'»@'+str(evidence[f.predicate_token_ref].start)
            if f.argument_token_refs:
                labels[name]+=' ('+', '.join(evidence[t].span for t in f.argument_token_refs)+')'
            row=normalize(asdict(f));sem=row['semantic']
            sem.pop('component_scope_tree',None);sem.pop('component_scope_label',None)
            args=sem.pop('proposition_args',{})
            for role,arg in args.items():
                if set(arg)-{'frame_ref','tree','attitude'}:return None
                if arg.get('tree'):
                    # Argument is normalized already: scope's Ref map accepts
                    # normalized names as well as physical frame IDs.
                    refs.update({v:v for v in names.values()})
                    try:child=scope(arg['tree'])
                    except (ValueError,KeyError):return None
                else:child=arg.get('frame_ref')
                if child not in names.values() and not arg.get('tree'):return None
                edge={'parent':name,'role':role,'child':child,'attitude':arg.get('attitude')}
                edges[digest(edge)]=edge
                parents.setdefault(child,set()).add(name)
            for arg in sem.get('nominal_args',()):
                parents.setdefault(arg['frame_ref'],set()).add(name)
            scopes=[];questions=[]
            for q in sem.get('component_questions',()):
                if q['kind']!='MODIFIER_SCOPE': questions.append(q);continue
                if not any(q.get('content_frame_ref')==a.get('frame_ref') or a.get('tree') for a in args.values()): return None
                scopes.append({k:v for k,v in q.items() if k!='content_frame_ref'})
            sem['component_questions']=questions
            sem['scope_properties']=scopes
            sem.pop('component_child',None)
            cores[name]=row
        for f in bundle:
            parent=f.semantic.get('component_child')
            if parent and refs.get(parent) not in parents.get(names[f.frame_id],set()): return None
        projections.append((cores,edges))
    if any(cores!=projections[0][0] for cores,edges in projections[1:]): return None
    pools=[set(edges) for cores,edges in projections]
    if len({tuple(sorted(p)) for p in pools})!=len(pools): return None
    common=set.intersection(*pools);options=[]
    for bundle,(_,edges) in zip(bundles,projections):
        delta=[edges[k] for k in sorted(set(edges)-common)]
        if not delta or len(delta)>8: return None
        label='; '.join(labels[e['parent']]+' scopes over '+labels[e['child']]+
                       ' ['+e['role']+', attitude='+str(e['attitude'])+']' for e in delta)
        options.append({'candidate_id':bundle[-1].frame_id,'label':label})
    return {'options':options,'question':'Only scope links differ; roles, whole morphology and nominal dependencies are fixed. '
            'BOTH means joint descriptions of the SAME event, not separate event occurrences. '
            'Which immediate scope links are supported by this source? Do not assume that lexical modifiers commute.',
            'backbone_hash':digest(projections[0][0]),'candidate_edges':{
                bundle[-1].frame_id:list(edges.values()) for bundle,(_,edges) in zip(bundles,projections)},
            'common_edge_ids':sorted(common)}
