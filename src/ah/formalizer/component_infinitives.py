"""Compose bounded infinitive areas through released slots and closed probes."""
from .canonical_ledger import digest
from .component_probe import _probe


def compose(state, release, selector, region, tokens, cfg, depth):
    from .component_refinement import compose_area, region_for, root, accepted, block
    starts=[i for i,t in enumerate(tokens) if any(v.pos=='INFN' for v in t.variants)]
    if not starts:return None
    policy=cfg.get('infinitive_composition')
    if not policy:
        return block(state,region,[],'COMPONENT_INFINITIVE_UNSUPPORTED')
    options={}
    for start in starts:
        ends={len(tokens)}|{i for i in range(start+1,len(tokens)) if any(v.pos=='VERB' for v in tokens[i].variants)}
        for end in sorted(ends):
            if start==0 and end==len(tokens):continue
            cid=digest([region.region_id,start,end])
            options[cid]=(start,end)
    if not options or len(options)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
        return block(state,region,[],'COMPONENT_INFINITIVE_SEARCH_INCOMPLETE')
    choices=[{'candidate_id':cid,'label':'Infinitive area «'+state.text[tokens[a].start:tokens[b-1].end]+
        '»; remaining parent «'+' '.join(t.span for t in [*tokens[:a],*tokens[b:]])+'»'} for cid,(a,b) in options.items()]
    key=region.region_id+'|infinitive-boundary'
    chosen=_probe(state,selector,release,key,'component_attachment',choices,state.text[slice(*region.source_range)],region.source_range,
        question='Select the full dependent infinitive area including its complements; the remaining parent must remain a clause. '
        'A boundary does not establish the relation, the controller or occurrence of the infinitive event.')
    state.syntax_trace.append({'kind':'INFINITIVE_BOUNDARY','decision_ref':key,'options':options,'selected':chosen})
    if chosen is None:return block(state,region,[],'COMPONENT_INFINITIVE_UNRESOLVED')
    a,b=options[chosen]; body=tokens[a:b];parent=[*tokens[:a],*tokens[b:]]
    if not parent:return block(state,region,[],'COMPONENT_INFINITIVE_UNRESOLVED')
    pr=region_for(state,region,parent,'INFINITIVE_PARENT')
    frames=compose_area(state,release,selector,pr,parent,cfg,depth+1)
    if root(frames) is None:return block(state,region,frames,'COMPONENT_INFINITIVE_PARENT_UNRESOLVED')
    # Shared implicit identity is one existing licensed slot, not a new subject.
    owners=[f for f in accepted(frames) if f.semantic.get('implicit_arguments',{}).get(cfg['subject_role'],{}).get('license')=='SUBJECT_AGREEMENT']
    links={digest([f.frame_id,r]):(f,r) for f in owners for r in policy['relations']
           if r['role'] not in f.semantic.get('proposed_roles',{}).values() and r['role'] not in f.semantic.get('proposition_args',{})}
    if not links or len(links)>cfg['max_candidates']:
        return block(state,region,frames,'COMPONENT_INFINITIVE_CONTROL_UNRESOLVED')
    choices=[{'candidate_id':cid,'label':'«'+body[0].span+'» fills '+r['role']+' of «'+f.anchor_span+
        '»; its omitted subject is the SAME omitted '+cfg['subject_role']+' of that predicate; attitude='+r['attitude']+
        '; does not assert that the infinitive event occurred'} for cid,(f,r) in links.items()]
    key=region.region_id+'|infinitive-link'
    chosen=_probe(state,selector,release,key,'component_attachment',choices,state.text[slice(*region.source_range)],region.source_range,
        question='Select a source-supported infinitive relation AND subject control. PURPOSE is a goal, not an accomplished event. '
        'A complement may have a different controller: if no candidate represents the source, answer 0 or ?. Do not assign identity from proximity.')
    if chosen is None:return block(state,region,frames,'COMPONENT_INFINITIVE_CONTROL_UNRESOLVED')
    owner,relation=links[chosen]
    alias={'frame_ref':owner.frame_id,'role':cfg['subject_role']}
    cr=region_for(state,region,body,'INFINITIVE')
    children=compose_area(state,release,selector,cr,body,cfg,depth+1,infinitive=alias)
    content=root(children)
    if content is None:return block(state,region,[*frames,*children],'COMPONENT_INFINITIVE_CHILD_UNRESOLVED')
    from .modifier_scope_shapes import argument
    owner.semantic.setdefault('proposition_args',{})[relation['role']]=argument(content,relation['attitude'])
    content.semantic['component_child']=owner.frame_id
    state.syntax_trace.append({'kind':'INFINITIVE_ATTACHMENT','decision_ref':key,'owner_ref':owner.frame_id,
        'content_ref':content.frame_id,'relation':relation,'controller':alias,
        'parent_token_refs':[t.token_id for t in parent],'content_token_refs':[t.token_id for t in body]})
    return [*frames,*children]
