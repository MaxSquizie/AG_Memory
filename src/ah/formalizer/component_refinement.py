"""Refine an already selected nominal slot with a recursively composed area."""
from .probe_wording import reading as describe_reading
from .probe_wording import role as role_text
from copy import deepcopy
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe
from .regions import TextRegion
from .state import FrameCandidate
from .composition_tree import internalize


def region_for(state, parent, tokens, label):
    child = TextRegion('region:'+digest([parent.region_id,label,[t.token_id for t in tokens]]),
        'CLAUSE',(min(t.start for t in tokens),max(t.end for t in tokens)),tuple(t.token_id for t in tokens),parent.region_id,
        grounds=('MORPHOLOGICAL_REFINEMENT',))
    if not any(r.region_id==child.region_id for r in state.region_forest.regions):
        state.region_forest.regions.append(child)
    return child


def accepted(frames):
    return [f for f in frames if not f.semantic.get('structural_unresolved')]


def root(frames):
    from .composition_tree import roots
    found = roots(frames)
    return found[0] if len(found) == 1 else None


def block(state, region, frames, reason):
    state.diag(reason, region.region_id)
    for f in frames: f.semantic['structural_unresolved']=True
    return frames


def compose_area(state, release, selector, region, tokens, cfg, depth=0, attachment=None, infinitive=None, request=None):
    from .composition_session import current, child_key
    runtime=current(state)
    from .morphology_domain import project
    key=child_key(region,tokens,attachment,infinitive,request)
    def calculate():
        local=project(state,tokens)
        if runtime:
            from .composition_morphology import prepare
            local=prepare(runtime,region,tokens,request,cfg)
            runtime.area_inputs=(region,local,request)
        frames=_compose_area(state,release,selector,region,local,cfg,depth,attachment,infinitive,request)
        from .partial_composition import propagate
        propagate(state,region,frames)
        from .scope_boundaries import retain
        try:retain(state,region,frames)
        except ValueError as exc:
            block(state,region,frames,str(exc))
        from .composition_tree import roots
        selected_roots=roots(frames)
        if len(selected_roots)==1:
            # Retain the accepted construction's source envelope, including
            # connectors/delimiters which do not belong to lexical child frames.
            selected_roots[0].semantic['composition_source_range']=list(region.source_range)
        if runtime:runtime.sources.retain(key,region,local,frames,request)
        return frames
    def compute():
        if not runtime:return calculate()
        with runtime.area(region,tokens,request):return calculate()
    if not runtime:return compute()
    from .composition_dispatcher import DispatchBlocked
    with runtime.area(region,tokens,request):
        try:
            result=runtime.child(key,compute,[tokens,request,cfg,attachment,infinitive])
        except DispatchBlocked as exc:
            return block(state,region,[],str(exc))
        version=runtime.dispatcher.nodes['child:'+key]['revision']
        for frame in result:
            frame.semantic['dispatch_task']={'task_ref':'child:'+key,'revision':version}
        return result


def _compose_area(state, release, selector, region, tokens, cfg, depth=0, attachment=None, infinitive=None, request=None):
    from .structural_tasks import enabled
    if enabled(release):
        if depth>=cfg.get('refinement',{}).get('max_depth',release.entries('ProposalPolicy')[0]['max_depth']):
            return block(state,region,[],'COMPONENT_REFINEMENT_SEARCH_INCOMPLETE')
        from .relation_composition import compose
        from .structural_tasks import choose
        from .composition_tree import roots
        from .component_probe_replay import supersede
        import json
        attempts=set()
        for revision in range(cfg.get('refinement',{}).get('max_depth',16)):
            begin=len(state.syntax_trace);diagnostics_begin=len(state.diagnostics)
            if revision:
                from .composition_session import current as current_session
                runtime=current_session(state)
                if runtime:
                    runtime.dispatcher.discard_attempt()
                    from .composition_morphology import prepare
                    tokens=prepare(runtime,region,tokens,request,cfg)
                    runtime.area_inputs=(region,tokens,request)
            # Feedback concerns this region. Child inputs carry their own typed
            # constraints; an ancestor's failed split is not child evidence.
            child_cfg={k:v for k,v in cfg.items() if k not in {'_task_constraints','_task_constraints_text','_partition_rejections'}}
            result=compose(state,release,selector,region,tokens,{**cfg,'_depth':depth},request,
                lambda owned,slot:compose_area(state,release,selector,region_for(state,region,owned,'RELATION_CHILD'),
                    owned,child_cfg,depth+1,attachment=attachment,
                    infinitive=(None if slot and slot.independent_subject else slot.controller if slot and slot.controller else infinitive),
                    request=slot))
            from .composition_contracts import LexicalRoute,conflicts,record_failure
            route=result if isinstance(result,LexicalRoute) else None
            if result is None or route is not None:
                if route:route.validate(state,region,tokens)
                result=_compose_lexical_area(state,release,selector,region,tokens,
                    {**cfg,'_literal_relation':True},depth,attachment,infinitive,request)
                route_ok=not route or route.accept(state,region,result)
                from .content_reference_functions import omitted_content
                if route_ok:result=omitted_content(state,release,selector,region,tokens,cfg,request,result,
                    lambda owned,slot:compose_area(state,release,selector,region_for(state,region,owned,'RELATION_CHILD'),
                        owned,child_cfg,depth+1,attachment=attachment,
                        infinitive=(None if slot and slot.independent_subject else slot.controller if slot and slot.controller else infinitive),request=slot))
            tasks=[r for r in state.syntax_trace[begin:] if r.get('kind')=='STRUCTURAL_TASK']
            if len(roots(result))==1:
                return result
            reasons=[d.code for d in state.diagnostics[diagnostics_begin:]]
            if any(c in reasons for c in ('STRUCTURAL_REVISION_NO_PROGRESS','PARTITION_OWNERSHIP_UNRESOLVED')):return result
            from .composition_session import current as current_session
            runtime=current_session(state)
            used=runtime.tasks.reads[-1]['probes'] if runtime and runtime.tasks.reads else set()
            pending_context=any(state.component_probe_records.get(k,{}).get('decision',{}).get('selector_outcome')
                in {'MULTIPLE_ADMISSIBLE','INSUFFICIENT_CONTEXT'} and not state.component_probe_records[k].get('superseded_by') for k in used)
            # Unknown context, invalid responses, resources and budgets are
            # not invitations to guess another interpretation.
            if (not any(r.get('slot')=='structural_relation' and r.get('selected') for r in tasks)
                    or pending_context or any(r.get('status') in {'PENDING','BLOCKED'} for r in tasks)
                    or any('INCOMPLETE' in c or c in {'RESOURCE_MISSING','ARITHMETIC_QUANTIFIER_DEFERRED',
                        'COMPONENT_PROBE_FAILED','COMPUTATION_LIMIT','COMPOSITION_PRODUCER_PENDING','VALENCY_UNKNOWN','INTEGRITY_ERROR'} for c in reasons)):
                return result
            failures=conflicts(state,region,begin)
            # Existing dependency narrowing reports an explicit empty constrained
            # domain, not an arbitrary diagnostic containing a magic substring.
            witnesses=[r for r in state.syntax_trace[begin:] if r.get('kind')=='DEPENDENCY_REJECTED'
                       and r.get('region_ref')==region.region_id and r.get('empty_domains')]
            if route and witnesses:
                failures.append(record_failure(state,region,'LOCAL_DEPENDENCY_CONFLICT',route.proof,
                    'A proposed lexical dependency assignment has an empty constrained domain. '
                    'This does not prove that every interpretation of the source is impossible.',
                    witnesses,search_complete=False))
            if not failures:
                state.diag('STRUCTURAL_IMPLEMENTATION_GAP',region.region_id)
                return result
            local_tasks=[r for r in tasks if r.get('region_ref')==region.region_id]
            constraints=json.dumps({'attempted_choices':[
                {'slot':r['slot'],'value':next((v for v in r.get('alternatives',()) if v['candidate_id']==r.get('selected')),None)}
                for r in local_tasks if r.get('selected')], 'failures':failures},ensure_ascii=False,sort_keys=True)
            local_regions={region.region_id,*(r.get('region_ref') for r in tasks)}
            related=used if runtime else {k for k in state.decisions if any(k.startswith(r+'|') for r in local_regions if r)}
            nonstructural=[(k,d.candidates,d.selected,d.selector_outcome) for k in sorted(related)
                if (d:=state.decisions.get(k)) is not None and not d.slot_id.startswith('structural_')]
            signature=digest([[(r.get('region_ref'),r['slot'],r.get('selected'),r.get('reason'),
                [v['candidate_id'] for v in r.get('alternatives',())]) for r in tasks],sorted(set(reasons)),
                nonstructural,[(f.frame_id,f.semantic) for f in result]])
            if signature in attempts:
                state.syntax_trace.append({'kind':'STRUCTURAL_REVISION_STALLED','region_ref':region.region_id,
                    'source_range':list(region.source_range),'attempts':revision+1})
                return block(state,region,result,'STRUCTURAL_REVISION_NO_PROGRESS')
            attempts.add(signature)
            selected_descriptions=[v['label'] for r in local_tasks if r.get('selected') and r.get('slot')=='structural_relation'
                for v in r.get('alternatives',()) if v['candidate_id']==r['selected']]
            selected_descriptions.extend(f['witness']['proposal']['label'] for f in failures
                if isinstance(f.get('witness'),dict) and f['witness'].get('proposal',{}).get('label'))
            uncovered={tid for f in result for tid in f.semantic.get('uncovered_token_refs',())}
            uncovered.update(tid for r in state.syntax_trace[begin:] if r.get('kind')=='STRUCTURAL_PARTITION_COVERAGE'
                             for tid in r.get('uncovered_token_refs',()))
            constraint_text='Tried: '+'; '.join(dict.fromkeys(selected_descriptions))+'. No complete parse was built.'
            constraint_text+=' Violated obligations: '+'; '.join(f['explanation'] for f in failures)
            if uncovered:
                constraint_text+=' Uncovered words: «'+' '.join(t.span for t in tokens if t.token_id in uncovered)+'».'
            constraint_text+=' This may be a parser limitation; failure alone does not prove that the reading is wrong. Repeating the same choices is not a revision.'
            revision_choice=choose(state,release,selector,region,cfg,'structural_revision',[
                {'candidate_id':'REVISE','label':'The text supports a different relation or different boundaries; reconsider them'},
                {'candidate_id':'DEFER','label':'No different reading is supported; leave the parse unresolved'}],
                constraint_text+' Does the text support revising these choices?')
            if not revision_choice or revision_choice[0]['candidate_id']!='REVISE':return result
            # Retire this area's superseded decisions, not unrelated children.
            # The next attempt drops old dispatch reads and obtains fresh ones.
            replacement=revision_choice[1]['decision_ref']
            for key in {r['decision_ref'] for r in local_tasks if r.get('decision_ref')}:
                supersede(state,key,replacement)
                if runtime and 'probe:'+key in runtime.dispatcher.nodes:
                    runtime.dispatcher.invalidate('probe:'+key,'STRUCTURAL_HYPOTHESIS_REVISED')
            del state.diagnostics[diagnostics_begin:]
            cfg={**cfg,'_task_constraints':constraints,'_task_constraints_text':constraint_text,
                 '_partition_rejections':[f for f in failures if f['category']=='PARTITION_REJECTED']}
        return block(state,region,result,'STRUCTURAL_TASK_SEARCH_INCOMPLETE')
    return _compose_lexical_area(state,release,selector,region,tokens,cfg,depth,attachment,infinitive,request)


def _compose_lexical_area(state, release, selector, region, tokens, cfg, depth=0, attachment=None, infinitive=None, request=None):
    from .composition_session import current
    runtime=current(state)
    if runtime and not cfg.get('_skip_reuse'):
        reused=runtime.sources.reuse(region,tokens,attachment,infinitive,request)
        if cfg.get('_literal_relation'):
            if state.grammar_search_incomplete:
                state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                    'source_range':list(region.source_range),'slot':'child_slot','status':'BLOCKED',
                    'reason':'GRAMMAR_SEARCH_LIMIT','examined':0})
                return block(state,region,[],'COMPONENT_SEARCH_INCOMPLETE')
            from .composition_source_union import merge
            before=len(state.diagnostics)
            built=_compose_lexical_area(state,release,selector,region,tokens,
                {**cfg,'_skip_reuse':True},depth,attachment,infinitive,request)
            return merge(state,release,selector,region,tokens,cfg,reused,built,before)
        if reused is not None:
            if len(runtime.sources.alternatives(tokens))>1:
                from .composition_children import select_child
                select_child(state,release,selector,region,reused,'SOURCE_PROPOSITION',
                    'Select one complete source alternative preserving its linked morphology and scope.')
            return reused
    from .refinement_boundaries import select, agreeing
    from .component_predication import compose_alternatives
    tokens=list(tokens)
    if depth>=cfg.get('refinement',{}).get('max_depth',release.entries('ProposalPolicy')[0]['max_depth']):
        return block(state,region,[],'COMPONENT_REFINEMENT_SEARCH_INCOMPLETE')
    from .attitude_composition import compose as compose_attitude
    attitude_frames=None if cfg.get('_literal_relation') else compose_attitude(state,release,selector,region,tokens,cfg,request,
        lambda owned,slot:compose_area(state,release,selector,region_for(state,region,owned,'ATTITUDE_CHILD'),
                                      owned,cfg,depth+1,request=slot))
    if attitude_frames is not None:return attitude_frames
    from .composition_boundaries import select as select_outer_boundary
    outer = None if cfg.get('_literal_relation') else select_outer_boundary(state,release,selector,region,tokens,cfg)
    if outer is False:
        return block(state,region,[],'COMPOSITION_BOUNDARY_UNRESOLVED')
    if outer is not None and outer['kind']=='CONNECTIVE':
        from .component_coordination import coordinate
        return coordinate(state,release,selector,region,tokens,[],cfg,[],boundary=outer['span'],
            compose_child=lambda area,owned:compose_area(state,release,selector,area,owned,cfg,
                depth+1,attachment,infinitive,request),
            inside_attitude=bool(request and request.inside_attitude))
    from .operator_composition import compose as compose_operator
    operator_frames=None if cfg.get('_literal_relation') else compose_operator(state,release,selector,region,tokens,cfg,
        lambda owned,slot:compose_area(state,release,selector,region_for(state,region,owned,'OPERATOR_CONTENT'),
                                  owned,cfg,depth+1,attachment,infinitive,slot),request=request,
        outer=outer['operator'] if outer is not None else None)
    if operator_frames is not None:
        return operator_frames
    from .relative_composition import compose as compose_relative
    from dataclasses import replace
    relative_frames=None if cfg.get('_literal_relation') else compose_relative(state,release,selector,region,tokens,cfg,
        lambda owned,slot:compose_area(state,release,selector,region_for(state,region,owned,'TYPED_CHILD'),
            owned,cfg,depth+1,attachment if slot is None else None,infinitive if slot is None else None,
            replace(slot,inside_attitude=bool(request and request.inside_attitude)) if slot is not None else request))
    if relative_frames is not None:
        return relative_frames
    from .component_area_scope import allowed, connectives
    if not allowed(state,release,region,tokens,conjunction=True,inside_attitude=bool(request and request.inside_attitude),literal_scope=cfg.get('_literal_relation',False)):
        return block(state,region,[],'COMPONENT_SCOPE_UNRESOLVED')
    # A participating head is already owned by this area, not a nested start.
    participial=isinstance(attachment,tuple)
    search_tokens=tokens[1:] if participial else tokens
    boundary=cfg.get('_selected_refinement')
    cfg={k:v for k,v in cfg.items() if k!='_selected_refinement'}
    if boundary is None and not cfg.get('_literal_relation'):
        boundary=select(state,release,selector,region,search_tokens,cfg) if cfg.get('refinement') else None
    if boundary is False: return block(state,region,[],'COMPONENT_REFINEMENT_UNRESOLVED')
    if boundary is None:
        from .action_descriptions import passive_rule
        descriptive=bool(request and request.description_context)
        passive_heads=[t for t in tokens if any(passive_rule(v,cfg) for v in t.variants)]
        # A dependent infinitive requires a possible lexical parent. With no
        # parent, retain the whole area as a predication candidate instead of
        # requiring its object to become a fictitious parent clause.
        has_parent=any(v.pos in {'VERB','ADJS','PRED'} or v.pos=='ADJF' and 'nom' in v.cases
                       for t in tokens for v in t.variants)
        if not passive_heads and has_parent and attachment is None and infinitive is None and (request is None or
                request.output_sort=='PROPOSITION' and request.agreement_source is None):
            from .component_infinitives import compose as compose_infinitive
            nested=compose_infinitive(state,release,selector,region,tokens,cfg,depth,request=request)
            if nested is not None:return nested
        if request is not None and request.output_sort=='EVENT_DESCRIPTION':
            predicates=[]
        elif request is not None and request.agreement_source is not None:
            predicates=[t for t in tokens if any(v.pos=='INFN' for v in t.variants)] + passive_heads
        elif participial:
            predicates=[tokens[0]]
        elif infinitive:
            predicates=[t for t in tokens if any(v.pos=='INFN' for v in t.variants)
                        and (not request or not request.head_ref or request.head_ref==t.token_id)]
        else:
            from .component_predication import impersonal_predicate
            predicates=[t for t in tokens if any(v.pos=='VERB' and v.mood!='imperative' or
                v.pos in cfg.get('quality_predicate_pos',()) or impersonal_predicate(v,cfg) for v in t.variants)]
            from .component_predication import nominal_predicates
            predicates.extend(t for t in [*nominal_predicates(tokens,cfg),*passive_heads] if t not in predicates)
            if descriptive:
                predicates.extend(t for t in tokens if t not in predicates and
                    (t in passive_heads or any(v.pos=='INFN' for v in t.variants)))
        nominal_groups=[]
        if connectives(state,release,region,tokens):
            from .component_nominal_groups import select as select_nominal_groups
            nominal_groups=select_nominal_groups(state,release,selector,region,tokens,cfg)
            if nominal_groups is False:
                return block(state,region,[],'COMPONENT_NOMINAL_COORDINATION_UNRESOLVED')
        if nominal_groups is None:
            from .component_coordination import coordinate
            return coordinate(state,release,selector,region,tokens,predicates,cfg,[],
                compose_child=lambda area,owned:compose_area(state,release,selector,area,owned,cfg,depth+1,request=request),
                inside_attitude=bool(request and request.inside_attitude))
        frames=compose_alternatives(state,release,selector,region,tokens,predicates,cfg,attachment=attachment,nominal_groups=nominal_groups,infinitive=infinitive,request=request)
        for f in frames:
            f.semantic['owned_token_refs']=[t.token_id for t in tokens]
        return frames
    offset=int(participial)
    if 'body_refs' in boundary:
        body=[t for t in tokens if t.token_id in boundary['body_refs']]
        parent=[t for t in tokens if t.token_id not in boundary['body_refs']]
        a,b=tokens.index(body[0]),tokens.index(body[-1])+1
        if boundary.get('marker_ref'):
            marker=next(t for t in body if t.token_id==boundary['marker_ref'])
            body=[marker,*[t for t in body if t is not marker]]
    else:
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
    frames=compose_area(state,release,selector,pr,parent,cfg,depth+1,attachment,infinitive,request)
    from .composition_children import select_child
    parent_root=select_child(state,release,selector,region,frames,'REFINEMENT_PARENT',
        'This parent contains the nominal described by «'+state.text[body[0].start:body[-1].end]+'».')
    if parent_root is None: return block(state,region,frames,'COMPONENT_REFINEMENT_PARENT_UNRESOLVED')
    evidence={t.token_id:t for t in state.evidence}
    hosts={}
    for frame in accepted(frames):
        for tid in frame.argument_token_refs:
            h=evidence[tid]
            if h.start>=body[0].start and not cfg.get('_literal_relation'): continue
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
    if boundary['kind']=='RELATIVE_PRONOUN' or boundary['kind']=='RELATIVE' and boundary['rule'].get('POS')=='ADJF':
        from .relative_pronoun import compose as compose_relative
        children,host_frame=compose_relative(state,release,selector,region,body,owner,host,reading,boundary['rule'],cfg,depth)
        description=select_child(state,release,selector,region,children,'NOMINAL_DESCRIPTION',
            'This area describes the established nominal «'+host.span+'»; preserve its selected morphology and reference.')
        if description is None or host_frame is None:
            return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_CHILD_UNRESOLVED')
        host_role=host_frame.semantic['refinement_binding']['host_role']
    elif boundary['kind']=='RELATIVE':
        marker=body[0];link_refs=boundary.get('marker_refs') or [marker.token_id]
        child_tokens=[t for t in body if t.token_id not in link_refs]
        if not child_tokens: return block(state,region,frames,'COMPONENT_REFINEMENT_UNRESOLVED')
        cr=region_for(state,region,child_tokens,'RELATIVE')
        children=compose_area(state,release,selector,cr,child_tokens,cfg,depth+1)
        content=select_child(state,release,selector,region,children,'RELATIVE_PROPOSITION',
            'This area is linked to the established nominal «'+host.span+'» by «'+marker.span+'».')
        if content is None: return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_CHILD_UNRESOLVED')
        rule=boundary['rule']
        variants=[v for v in marker.variants if rule.get('general') or v.pos==rule['POS'] and v.lemma==rule['lemma']]
        # Non-equivalent whole readings are not silently selected.
        unique={digest({k:v for k,v in _morph(m).items() if k!='score'}):m for m in variants}
        if len(unique)!=1:
            if not cfg.get('_literal_relation'):return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_MARKER_UNRESOLVED')
            from .structural_tasks import choose
            selected=choose(state,release,selector,region,cfg,'structural_marker_reading',
                [{'candidate_id':cid,'reading':_morph(v),'label':describe_reading(_morph(v))} for cid,v in unique.items()],
                'Choose the whole reading of the source connector under the selected host and child constraints.')
            if not selected:return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_MARKER_UNRESOLVED')
            unique={selected[0]['candidate_id']:unique[selected[0]['candidate_id']]}
        sem=deepcopy(content.semantic)
        sem={k:sem[k] for k in ('component_region',) if k in sem}
        from .modifier_scope_shapes import argument
        sem.update(proposed_roles={chosen:cfg['nominal_host_role']},morph_bindings={chosen:_morph(reading),marker.token_id:_morph(next(iter(unique.values())))},
            lexical_units={chosen:deepcopy(owner.semantic['lexical_units'].get(chosen,{'head_ref':chosen,'anchor_refs':[chosen],'surface':host.span,'mention_ref':chosen}))},
            proposition_args={cfg['modifier_content_role']:argument(content,'UNKNOWN')},
            structural_unresolved=False,missing_required_roles=[],uncovered_token_refs=[],component_questions=[],
            preposition_bindings={},relative_temporal=[],requires_attachment_probe=False,owned_token_refs=list(link_refs),nominal_description=True)
        sem['lexical_units'][marker.token_id]={'head_ref':marker.token_id,'anchor_refs':list(link_refs),
            'surface':' '.join(evidence[r].span for r in link_refs),'mention_ref':'relation:'+digest(link_refs)}
        description=FrameCandidate('component-relative:'+digest([marker.token_id,chosen,content.frame_id]),'FLAT',marker.span,
            (marker.span,host.span),(host.span,),construction='COMPONENTS_V1',predicate_token_ref=marker.token_id,
            argument_token_refs=(chosen,),source_range=(marker.start,body[-1].end),semantic=sem,provenance=owner.provenance)
        internalize(children,content,description)
        children.append(description); host_frame=description
        host_role=cfg['nominal_host_role']
    else:
        cr=region_for(state,region,body,'PARTICIPLE')
        binding=(host,reading,*([selected_group[3]] if selected_group else []))
        if boundary['kind']=='BOUND_DESCRIPTION':
            from .structural_tasks import choose
            selected_role=choose(state,release,selector,region,cfg,'structural_description_role',[
                {'candidate_id':r['role_id'],'label':r['role_id']+': '+role_text(r['role_id'])} for r in release.entries('RoleRegistry')],
                'Which participant role does «'+host.span+'» fill inside «'+' '.join(t.span for t in body)+'»?')
            if not selected_role:return block(state,region,frames,'COMPONENT_REFINEMENT_HOST_UNRESOLVED')
            binding={'kind':'BOUND_DESCRIPTION','host':host,'reading':reading,
                     'host_role':selected_role[0]['candidate_id'],'proof':selected_role[1]}
        children=compose_area(state,release,selector,cr,body,cfg,depth+1,binding)
        description=select_child(state,release,selector,region,children,'NOMINAL_DESCRIPTION',
            'This area describes the established nominal «'+host.span+'»; preserve its selected morphology and reference.')
        candidates=[f for f in accepted(children) if f.semantic.get('refinement_binding',{}).get('host_token_ref')==chosen]
        if description is None or len(candidates)!=1:
            return block(state,region,[*frames,*children],'COMPONENT_REFINEMENT_CHILD_UNRESOLVED')
        host_frame=candidates[0];host_role=host_frame.semantic['refinement_binding']['host_role']
        # Reuse the exact nominal unit/mention of the already assembled host.
        if not selected_group:
            host_frame.semantic['lexical_units'][chosen]=deepcopy(owner.semantic['lexical_units'][chosen])
    internalize(children,description,owner)
    owner.semantic.setdefault('nominal_args',[]).append({'host_token_ref':chosen,'host_role':host_role,
        'frame_ref':description.frame_id,'host_frame_ref':host_frame.frame_id,
        **({'tree':description.semantic['component_scope_tree']} if description.semantic.get('component_scope_tree') else {}),
        **({'scope_assumption':assumption} if assumption else {}),
        **({'host_group_member_refs':selected_group[3]['group']['member_refs']} if selected_group else {})})
    state.syntax_trace.append({'kind':'NOMINAL_REFINEMENT','parent_ref':owner.frame_id,
        'description_ref':description.frame_id,'host_token_ref':chosen,'kind_detail':boundary['kind'],
        'source_token_refs':[t.token_id for t in tokens],'parent_token_refs':[t.token_id for t in parent],
        'description_token_refs':[t.token_id for t in body],'separator_refs':sorted(set(separators))})
    return [*frames,*children]
