"""Compose bounded infinitive areas through released slots and closed probes."""
from .canonical_ledger import digest


def compose(state, release, selector, region, tokens, cfg, depth,request=None):
    from .component_refinement import compose_area, region_for, root, accepted, block
    starts=[i for i,t in enumerate(tokens) if any(v.pos=='INFN' for v in t.variants)]
    if not starts:return None
    policy=cfg.get('infinitive_composition')
    if not policy:
        return block(state,region,[],'COMPONENT_INFINITIVE_UNSUPPORTED')
    from .structural_tasks import choose,source_set
    choices=[{'candidate_id':'start:'+tokens[i].token_id,'index':i,'token_ref':tokens[i].token_id,
        'label':'Dependent infinitive starts at «'+tokens[i].span+'» @'+str(tokens[i].start)} for i in starts]
    if request and request.description_context:
        choices.append({'candidate_id':'WHOLE_ACTION_DESCRIPTION','label':
            'Whole target is one infinitive action description; no separate parent predicate inside TARGET'})
    selected=choose(state,release,selector,region,cfg,'infinitive_head',choices,
        'Select the head of a dependent infinitive inside TARGET, or the whole-target description '
        'when that is permitted. This selects a proposed head, not its subject or factual occurrence.')
    if not selected:return block(state,region,[],'COMPONENT_INFINITIVE_UNRESOLVED')
    if selected[0]['candidate_id']=='WHOLE_ACTION_DESCRIPTION':return None
    def admissible(part):
        used={t.token_id for t in part}
        return selected[0]['token_ref'] in used and any(
            t.token_id not in used and any(c.isalnum() for c in t.span) for t in tokens)
    boundary=source_set(state,release,selector,region,tokens,cfg,'infinitive_content',
        'Select the complete dependent infinitive content, including its complements. '
        'Exclude the parent predicate, its participants, and other clauses. '
        'The remaining parent must retain the predicate that takes this content. '
        'A boundary does not establish the controller or assert the action.',
        initial=selected,admissible=admissible)
    if not boundary:return block(state,region,[],'COMPONENT_INFINITIVE_UNRESOLVED')
    body,proofs=boundary;owned={t.token_id for t in body}
    parent=[t for t in tokens if t.token_id not in owned]
    state.syntax_trace.append({'kind':'INFINITIVE_BOUNDARY','head_proof':selected[1],
        'boundary_proofs':list(proofs),'content_token_refs':[t.token_id for t in body],
        'parent_token_refs':[t.token_id for t in parent]})
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
    if not links:
        return block(state,region,frames,'COMPONENT_INFINITIVE_CONTROL_UNRESOLVED')
    from .probe_wording import proposition_role
    head=tokens[selected[0]['index']]
    choices=[{'candidate_id':cid,'label':'«'+head.span+'» fills '+r['role']+' of «'+f.anchor_span+
        '» ('+proposition_role(r['role'])+')'+
        '; its omitted subject is the SAME '+label+' of that predicate; attitude='+r['attitude']+
        '; does not assert that the infinitive event occurred'} for cid,(f,r,alias,label) in links.items()]
    selected_link=choose(state,release,selector,region,cfg,'infinitive_link',choices,
        'Select a source-supported infinitive relation AND subject control. '
        'Distinguish what the parent predicate is about (OBJECT) from why a separate parent action is performed (PURPOSE). '
        'UNKNOWN leaves the status unspecified; HYPOTHETICAL presents the child as intended or possible. '
        'A complement may have a different controller: answer 0 if no candidate represents the source, or ? if the evidence is insufficient. Do not assign identity from proximity.')
    if not selected_link:return block(state,region,frames,'COMPONENT_INFINITIVE_CONTROL_UNRESOLVED')
    chosen=selected_link[0]['candidate_id'];key=selected_link[1]['decision_ref']
    owner,relation,alias,label=links[chosen]
    cr=region_for(state,region,body,'INFINITIVE')
    child_slot=InputSlot(inside_attitude=True,controller=alias,description_context=True,head_ref=head.token_id,
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
