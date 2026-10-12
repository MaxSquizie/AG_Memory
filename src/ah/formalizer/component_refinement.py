"""Refine an already selected nominal slot with a recursively composed area."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe
from .regions import TextRegion
from .state import FrameCandidate


def region_for(state, parent, tokens, label):
    child = TextRegion('region:'+digest([parent.region_id,label,[t.token_id for t in tokens]]),
        'CLAUSE',(tokens[0].start,tokens[-1].end),tuple(t.token_id for t in tokens),parent.region_id,
        grounds=('MORPHOLOGICAL_REFINEMENT',))
    state.region_forest.regions.append(child)
    return child


def accepted(frames):
    return [f for f in frames if not f.semantic.get('structural_unresolved')]


def root(frames):
    children = {c['frame_ref'] for f in frames for c in f.semantic.get('nominal_args',())}
    children.update(c['frame_ref'] for f in frames for c in f.semantic.get('proposition_args',{}).values())
    roots = [f for f in accepted(frames) if f.frame_id not in children and not f.semantic.get('component_child')]
    return roots[0] if len(roots)==1 else None


def block(state, region, frames, reason):
    state.diag(reason, region.region_id)
    for f in frames: f.semantic['structural_unresolved']=True
    return frames


def compose_area(state, release, selector, region, tokens, cfg, depth=0, attachment=None, infinitive=None):
    from .refinement_boundaries import select, agreeing
    from .component_predication import compose_alternatives
    tokens=list(tokens)
    if depth>=cfg['refinement']['max_depth']:
        return block(state,region,[],'COMPONENT_REFINEMENT_SEARCH_INCOMPLETE')
    from .component_area_scope import allowed, connectives
    if not allowed(state,release,region,tokens,conjunction=True):
        return block(state,region,[],'COMPONENT_SCOPE_UNRESOLVED')
    # A participating head is already owned by this area, not a nested start.
    participial=isinstance(attachment,tuple)
    search_tokens=tokens[1:] if participial else tokens
    boundary=select(state,release,selector,region,search_tokens,cfg)
    if boundary is False: return block(state,region,[],'COMPONENT_REFINEMENT_UNRESOLVED')
    if boundary is None:
        if attachment is None and infinitive is None:
            from .component_infinitives import compose as compose_infinitive
            nested=compose_infinitive(state,release,selector,region,tokens,cfg,depth)
            if nested is not None:return nested
        if participial or infinitive:
            predicates=[tokens[0]]
        else:
            predicates=[t for t in tokens if any(v.pos=='VERB' and v.mood!='imperative' or
                v.pos in cfg.get('quality_predicate_pos',()) for v in t.variants)]
        nominal_groups=[]
        if connectives(state,release,region,tokens):
            from .component_nominal_groups import select as select_nominal_groups
            nominal_groups=select_nominal_groups(state,release,selector,region,tokens,cfg)
            if nominal_groups is False:
                return block(state,region,[],'COMPONENT_NOMINAL_COORDINATION_UNRESOLVED')
        if nominal_groups is None:
            from .component_coordination import coordinate
            return coordinate(state,release,selector,region,tokens,predicates,cfg,[],
                compose_child=lambda area,owned:compose_area(state,release,selector,area,owned,cfg,depth+1))
        frames=compose_alternatives(state,release,selector,region,tokens,predicates,cfg,attachment=attachment,nominal_groups=nominal_groups,infinitive=infinitive)
        for f in frames:
            f.semantic['owned_token_refs']=[t.token_id for t in tokens]
        return frames
    offset=int(participial)
    a,b=boundary['start']+offset,boundary['end']+offset
    body=tokens[a:b]
    parent=[*tokens[:a],*tokens[b:]]
    # Consume boundary separators only. Internal punctuation is never erased.
    separators=[]
    while parent and parent[-1].span in {',','.'}:
        separators.append(parent.pop().token_id)
    while body and body[-1].span in {',','.'}:
        separators.append(body.pop().token_id)
    if b<len(tokens) and tokens[b].span==',':
        parent=[t for t in parent if t.token_id!=tokens[b].token_id]
        separators.append(tokens[b].token_id)
    if a and tokens[a-1].span==',':
        parent=[t for t in parent if t.token_id!=tokens[a-1].token_id]
        separators.append(tokens[a-1].token_id)
    if not parent or not body: return block(state,region,[],'COMPONENT_REFINEMENT_UNRESOLVED')
    pr=region_for(state,region,parent,'PARENT')
    frames=compose_area(state,release,selector,pr,parent,cfg,depth+1,attachment,infinitive)
    parent_root=root(frames)
    if parent_root is None: return block(state,region,frames,'COMPONENT_REFINEMENT_PARENT_UNRESOLVED')
    evidence={t.token_id:t for t in state.evidence}
    hosts={}
    for frame in accepted(frames):
        for tid in frame.argument_token_refs:
            h=evidence[tid]
            if h.start>=body[0].start: continue
            reading=frame.semantic.get('morph_bindings',{}).get(tid)
            if not reading: continue
            from .state import MorphVariant
            hv=MorphVariant(**{**reading,'cases':frozenset(reading['cases']),'features':frozenset(reading['features'])})
            if boundary['kind']=='PARTICIPLE' and not any(agreeing(hv,v) for v in body[0].variants if v.pos=='PRTF'): continue
            # One source mention can occur in several descriptions. Its owner
            # for this edge is the original slot, never a separate guessed M.
            hosts.setdefault(tid,(frame,h,hv))
    group_hosts={}
    if boundary['kind']=='PARTICIPLE':
        from .refinement_group_hosts import candidates as group_candidates
        group_hosts=group_candidates(accepted(frames),evidence,body)
    choices=[{'candidate_id':tid,'label':'Existing nominal «'+h.span+'» at '+str([h.start,h.end])}
             for tid,(_,h,_) in hosts.items()]
    choices.extend({'candidate_id':tid,'label':'WHOLE established group «'+h.span+'»'}
                   for tid,(_,h,_,_) in group_hosts.items())
    if len(choices)>cfg['max_candidates']:
        return block(state,region,frames,'COMPONENT_REFINEMENT_SEARCH_INCOMPLETE')
    chosen=_probe(state,selector,release,region.region_id+'|refinement-host','nominal_attachment',choices,
        state.text[slice(*region.source_range)],region.source_range,
        question='Which existing nominal does «'+state.text[body[0].start:body[-1].end]+
        '» describe? Choose its immediate host. Do not resolve pronoun identities or invent an entity.')
    assumption=None
    if chosen is None and boundary['kind']=='PARTICIPLE':
        from .refinement_uncertainty import select as select_assumption
        members={tid:[tid] for tid in hosts}
        members.update({tid:entry[3]['group']['member_refs'] for tid,entry in group_hosts.items()})
        assumption=select_assumption(state,release,region.region_id+'|refinement-host',choices,members,cfg)
        if assumption:chosen=assumption['selected']
    if chosen is None: return block(state,region,frames,'COMPONENT_REFINEMENT_HOST_UNRESOLVED')
    selected_group=group_hosts.get(chosen)
    owner,host,reading=selected_group[:3] if selected_group else hosts[chosen]
    if boundary['kind']=='RELATIVE' and boundary['rule']['POS']=='ADJF':
        from .relative_pronoun import compose as compose_relative
        children,host_frame=compose_relative(state,release,selector,region,body,owner,host,reading,boundary['rule'],cfg,depth)
        description=root(children)
        if description is None or host_frame is None:
            return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_CHILD_UNRESOLVED')
        host_role=host_frame.semantic['refinement_binding']['host_role']
    elif boundary['kind']=='RELATIVE':
        marker=body[0]; child_tokens=body[1:]
        if not child_tokens: return block(state,region,frames,'COMPONENT_REFINEMENT_UNRESOLVED')
        cr=region_for(state,region,child_tokens,'RELATIVE')
        children=compose_area(state,release,selector,cr,child_tokens,cfg,depth+1)
        content=root(children)
        if content is None: return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_CHILD_UNRESOLVED')
        rule=boundary['rule']
        variants=[v for v in marker.variants if v.pos==rule['POS'] and v.lemma==rule['lemma']]
        # Non-equivalent whole readings are not silently selected.
        unique={digest({k:v for k,v in _morph(m).items() if k!='score'}):m for m in variants}
        if len(unique)!=1: return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_MARKER_UNRESOLVED')
        sem=deepcopy(content.semantic)
        sem={k:sem[k] for k in ('component_region',) if k in sem}
        sem.update(proposed_roles={chosen:cfg['nominal_host_role']},morph_bindings={chosen:_morph(reading),marker.token_id:_morph(next(iter(unique.values())))},
            lexical_units={chosen:deepcopy(owner.semantic['lexical_units'].get(chosen,{'head_ref':chosen,'anchor_refs':[chosen],'surface':host.span,'mention_ref':chosen}))},
            proposition_args={cfg['modifier_content_role']:{'frame_ref':content.frame_id,'attitude':'UNKNOWN'}},
            structural_unresolved=False,missing_required_roles=[],uncovered_token_refs=[],component_questions=[],
            preposition_bindings={},relative_temporal=[],requires_attachment_probe=False,owned_token_refs=[marker.token_id],nominal_description=True)
        description=FrameCandidate('component-relative:'+digest([marker.token_id,chosen,content.frame_id]),'FLAT',marker.span,
            (marker.span,host.span),(host.span,),construction='COMPONENTS_V1',predicate_token_ref=marker.token_id,
            argument_token_refs=(chosen,),source_range=(marker.start,body[-1].end),semantic=sem,provenance=owner.provenance)
        content.semantic['component_child']=description.frame_id
        children.append(description); host_frame=description
        host_role=cfg['nominal_host_role']
    else:
        cr=region_for(state,region,body,'PARTICIPLE')
        children=compose_area(state,release,selector,cr,body,cfg,depth+1,(host,reading,*([selected_group[3]] if selected_group else [])))
        description=root(children)
        candidates=[f for f in accepted(children) if f.semantic.get('refinement_binding',{}).get('host_token_ref')==chosen]
        if description is None or len(candidates)!=1:
            return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_CHILD_UNRESOLVED')
        host_frame=candidates[0];host_role=host_frame.semantic['refinement_binding']['host_role']
        # Reuse the exact nominal unit/mention of the already assembled host.
        if not selected_group:
            host_frame.semantic['lexical_units'][chosen]=deepcopy(owner.semantic['lexical_units'][chosen])
    description.semantic['component_child']=owner.frame_id
    owner.semantic.setdefault('nominal_args',[]).append({'host_token_ref':chosen,'host_role':host_role,
        'frame_ref':description.frame_id,'host_frame_ref':host_frame.frame_id,
        **({'scope_assumption':assumption} if assumption else {}),
        **({'host_group_member_refs':selected_group[3]['group']['member_refs']} if selected_group else {})})
    state.syntax_trace.append({'kind':'NOMINAL_REFINEMENT','parent_ref':owner.frame_id,
        'description_ref':description.frame_id,'host_token_ref':chosen,'kind_detail':boundary['kind'],
        'source_token_refs':[t.token_id for t in tokens],'parent_token_refs':[t.token_id for t in parent],
        'description_token_refs':[t.token_id for t in body],'separator_refs':sorted(set(separators))})
    return [*frames,*children]
