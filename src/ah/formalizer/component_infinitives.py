"""Compose bounded infinitive areas through released slots and closed probes."""
from .canonical_ledger import digest
from .component_probe import _probe


def compose(state, release, selector, region, tokens, cfg, depth,request=None):
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
    standalone=bool(request and request.description_context and not any(
        v.pos=='VERB' and v.lemma not in cfg.get('copula_lemmas',()) for t in tokens for v in t.variants))
    if standalone:
        choices.append({'candidate_id':'WHOLE_ACTION_DESCRIPTION','label':
            'Whole target is one infinitive action description with its participants and attributes; no separate parent predicate'})
    key=region.region_id+'|infinitive-boundary'
    chosen=_probe(state,selector,release,key,'component_attachment',choices,state.text[slice(*region.source_range)],region.source_range,
        question='Select the full dependent infinitive area including its complements; the remaining parent must remain a clause. '
        +('Or select the whole-target description if there is no separate parent predicate. ' if standalone else '')+
        'A boundary does not establish the relation, the controller or occurrence of the infinitive event.')
    state.syntax_trace.append({'kind':'INFINITIVE_BOUNDARY','decision_ref':key,'options':options,'selected':chosen})
    if chosen is None:return block(state,region,[],'COMPONENT_INFINITIVE_UNRESOLVED')
    if chosen=='WHOLE_ACTION_DESCRIPTION':return None
    a,b=options[chosen]; body=tokens[a:b];parent=[*tokens[:a],*tokens[b:]]
    if not parent:return block(state,region,[],'COMPONENT_INFINITIVE_UNRESOLVED')
    pr=region_for(state,region,parent,'INFINITIVE_PARENT')
    from .composition_tree import InputSlot, internalize
    from dataclasses import replace
    from .composition_children import select_child
    frames=compose_area(state,release,selector,pr,parent,cfg,depth+1,request=replace(request or InputSlot(),
        pending_proposition_roles=(request.pending_proposition_roles if request else frozenset()) |
            frozenset(r['role'] for r in policy['relations'])))
    if select_child(state,release,selector,region,frames,'INFINITIVE_PARENT',
        'The parent must accept the retained infinitive child in a declared proposition slot.') is None:return block(state,region,frames,'COMPONENT_INFINITIVE_PARENT_UNRESOLVED')
    # Control binds an existing entity slot, explicit or implicit. The common
    # child composer still builds the infinitive and all its dependents.
    from .control_arguments import controllers as argument_controllers
    controllers=[(f,alias,label) for f in accepted(frames) for alias,label in argument_controllers(f)]
    links={digest([f.frame_id,r,alias]):(f,r,alias,label) for f,alias,label in controllers for r in policy['relations']
           if (f.semantic.get('allowed_proposition_roles') is None or r['role'] in f.semantic['allowed_proposition_roles'])
           and r['role'] not in f.semantic.get('proposed_roles',{}).values() and r['role'] not in f.semantic.get('proposition_args',{})}
    if not links or len(links)>cfg['max_candidates']:
        return block(state,region,frames,'COMPONENT_INFINITIVE_CONTROL_UNRESOLVED')
    from .probe_wording import proposition_role
    choices=[{'candidate_id':cid,'label':'«'+body[0].span+'» fills '+r['role']+' of «'+f.anchor_span+
        '» ('+proposition_role(r['role'])+')'+
        '; its omitted subject is the SAME '+label+' of that predicate; attitude='+r['attitude']+
        '; does not assert that the infinitive event occurred'} for cid,(f,r,alias,label) in links.items()]
    key=region.region_id+'|infinitive-link'
    chosen=_probe(state,selector,release,key,'component_attachment',choices,state.text[slice(*region.source_range)],region.source_range,
        question='Select a source-supported infinitive relation AND subject control. '
        'Distinguish what the parent predicate is about (OBJECT) from why a separate parent action is performed (PURPOSE). '
        'UNKNOWN leaves the status unspecified; HYPOTHETICAL presents the child as intended or possible. '
        'A complement may have a different controller: if no candidate represents the source, answer 0 or ?. Do not assign identity from proximity.')
    if chosen is None:return block(state,region,frames,'COMPONENT_INFINITIVE_CONTROL_UNRESOLVED')
    owner,relation,alias,label=links[chosen]
    cr=region_for(state,region,body,'INFINITIVE')
    child_slot=InputSlot(inside_attitude=True,controller=alias,description_context=True,
        pending_propositions={ref:roles for ref,roles in (request.pending_propositions or {}).items()
            if ref in {t.token_id for t in body}} if request else None,
        pending_proposition_sources={ref:refs for ref,refs in (request.pending_proposition_sources or {}).items()
            if ref in {t.token_id for t in body}} if request else None)
    children=compose_area(state,release,selector,cr,body,cfg,depth+1,infinitive=alias,request=child_slot)
    content=select_child(state,release,selector,region,children,'CONTROLLED_INFINITIVE',
        'The subject uses the already selected controller '+label+'.')
    if content is None:return block(state,region,[*frames,*children],'COMPONENT_INFINITIVE_CHILD_UNRESOLVED')
    from .modifier_scope_shapes import argument
    owner.semantic.setdefault('proposition_args',{})[relation['role']]=argument(content,relation['attitude'])
    owner.semantic['pending_proposition_roles']=[r for r in owner.semantic.get('pending_proposition_roles',()) if r!=relation['role']]
    internalize(children,content,owner)
    state.syntax_trace.append({'kind':'INFINITIVE_ATTACHMENT','decision_ref':key,'owner_ref':owner.frame_id,
        'content_ref':content.frame_id,'relation':relation,'controller':alias,
        'parent_token_refs':[t.token_id for t in parent],'content_token_refs':[t.token_id for t in body]})
    return [*frames,*children]
