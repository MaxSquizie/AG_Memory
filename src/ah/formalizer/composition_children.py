"""Parent constraints can resolve a deferred child without copying child trees."""
from .canonical_ledger import digest
from .composition_tree import roots
from .component_probe import _probe


def select_child(state,release,selector,region,frames,contract,context):
    from .composition_session import current
    runtime=current(state)
    allowed=runtime.sources.allowed(getattr(frames,'task_key',None)) if runtime else None
    found=[f for f in roots(frames) if allowed is None or f.frame_id in allowed]
    if len(found)==1:return found[0]
    domains={f.frame_id:f.semantic['composition_domain'] for f in frames
             if f.semantic.get('composition_domain')}
    if not domains:
        from .composition_session import current
        runtime=current(state)
        if runtime and runtime.tasks.resume(frames,contract,context,region.region_id):
            found=roots(frames)
            if len(found)==1:return found[0]
            domains={f.frame_id:f.semantic['composition_domain'] for f in frames
                     if f.semantic.get('composition_domain')}
        if not domains:return None
    allowed=runtime.sources.allowed(getattr(frames,'task_key',None)) if runtime else None
    domains={fid:d for fid,d in domains.items() if allowed is None or fid in allowed}
    if not domains:return None
    from .component_policy import policy
    cfg=policy(release)
    from .structural_tasks import enabled,choose
    general=enabled(release)
    if (not general and len(domains)>cfg['max_candidates']) or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
    options=[{'candidate_id':fid,'label':d['label'],**({'frame_refs':d['frame_refs']} if general else {})} for fid,d in domains.items()]
    key=region.region_id+'|child-slot:'+digest([contract,context,options])
    question=('Resolve this child under its parent constraint '+contract+'. '+context+
        ' Do not reparse accepted children or change their identities. '
        'Choose only if the parent/source context distinguishes the retained alternatives; '
        'mere need for a complete tree is not evidence. Preserve supported alternatives; use ? for insufficient evidence and 0 if none fits. ')
    if general:
        result=choose(state,release,selector,region,cfg,'child_slot',options,question)
        selected=result[0]['candidate_id'] if result else None
        if result:key=result[1]['decision_ref']
    else:
        selected=_probe(state,selector,release,key,'child_slot',options,
            state.text[slice(*region.source_range)],region.source_range,question=question)
    state.syntax_trace.append({'kind':'CHILD_DOMAIN_CONSTRAINT','decision_ref':key,
        'parent_contract':contract,'child_domain_refs':[d['decision_ref'] for d in domains.values()],
        'candidates':list(domains),'selected':selected})
    if selected not in domains:return None
    selected_refs=set(domains[selected]['frame_refs'])
    source_ids={f.semantic.get('composition_source_ref') for f in frames if f.semantic.get('composition_source_ref')}
    if source_ids:
        state.clarification_candidates[:]=[row for row in state.clarification_candidates
            if not (row.get('kind')=='STRUCTURE' and
                    {o['candidate_id'] for o in row.get('options',())}<=source_ids)]
        chosen_sources={f.semantic.get('composition_source_ref') for f in frames if f.frame_id in selected_refs}
        for source in source_ids-chosen_sources:
            state.reject(source,'COMPOSITION_SOURCE','Selected source alternative: '+selected)

    for cid,domain in domains.items():
        for frame in frames:
            if frame.frame_id in domain['frame_refs']:
                frame.semantic['composition_decision']=key
                frame.semantic['composition_bundle_root']=cid
    for frame in frames:
        if frame.frame_id in selected_refs:
            frame.semantic['structural_unresolved']=False
            frame.semantic['composition_decision']=key
            frame.semantic['parent_constraint_decision']=key
            from .morphology_domain import license_use,frame_readings
            for _,tid,reading in frame_readings(frame):license_use(state,tid,reading,key,selected)
    return next(f for f in frames if f.frame_id==selected)
