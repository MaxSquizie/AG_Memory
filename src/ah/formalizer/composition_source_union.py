"""Every applicable producer runs before the common child domain is closed."""
from .canonical_ledger import digest
from .composition_tree import roots


def merge(state,release,selector,region,tokens,cfg,grammar,components,diagnostics_before):
    grammar=list(grammar or ());components=list(components)
    state.syntax_trace.append({'kind':'COMPOSITION_PRODUCERS','region_ref':region.region_id,
        'source_range':list(region.source_range),'sources':[
            {'source':'GRAMMAR','frames':len(grammar)}, {'source':'COMPONENT','frames':len(components)}],
        'partial_diagnostics':[d.code for d in state.diagnostics[diagnostics_before:]]})
    from .partial_composition import close_alternatives
    local=state.diagnostics[diagnostics_before:]
    # Both routes share the same producer obligations, including an empty
    # grammar result. A resource failure is never negative domain evidence.
    from .task_contracts import produced,TaskOutcome
    receipt=produced('GRAMMAR',None,local)
    if receipt.outcome in {TaskOutcome.BLOCKED,TaskOutcome.INCOMPLETE}:
        all_frames=[*grammar,*components]
        for f in all_frames:f.semantic['structural_unresolved']=True
        state.syntax_trace.append({'kind':'COMPOSITION_UNION_PENDING','region_ref':region.region_id,
            'task_outcome':receipt.outcome.value,'diagnostics':[d.code for d in local]})
        return all_frames
    all_frames=[*grammar,*components];by_id={f.frame_id:f for f in all_frames};bundles=[]
    for group in (grammar,components):
        pending=[(f,f.semantic['composition_domain']) for f in group if f.semantic.get('composition_domain')]
        if pending:
            bundles.extend((root,[by_id[r] for r in d['frame_refs']],d['label']) for root,d in pending)
        else:
            found=roots(group)
            if len(found)==1:
                owned=[f for f in group if not f.semantic.get('structural_unresolved')]
                bundles.append((found[0],owned,'; '.join(f.anchor_span for f in owned)))
    if not roots(components) and not any(f.semantic.get('composition_domain') for f in components) and any(
            'UNRESOLVED' in d.code for d in local):
        for f in all_frames:f.semantic['structural_unresolved']=True
        from .composition_contracts import conflicts
        if not any(r['category']=='PRODUCER_UNSUPPORTED' for r in conflicts(state,region,0)):
            state.diag('COMPOSITION_PRODUCER_PENDING',region.region_id)
        return all_frames
    from .component_constraints import accepts_bundle
    retained=[]
    for root,owned,label in bundles:
        if accepts_bundle(state,region,tokens,owned):
            retained.append((root,owned,label))
        else:
            for f in owned:
                f.semantic['structural_unresolved']=True
                f.semantic['structural_rejection']='ESTABLISHED_SOURCE_CONSTRAINT_CONFLICT'
                f.semantic.pop('composition_domain',None)
            state.syntax_trace.append({'kind':'ESTABLISHED_SOURCE_CONSTRAINT_REJECTION',
                'region_ref':region.region_id,'frame_refs':[f.frame_id for f in owned]})
    bundles=retained
    if not bundles:return all_frames
    if not grammar:
        if not any('UNRESOLVED' in d.code for d in local):
            close_alternatives(state,region,components)
        return components
    from .composition_equivalence import coalesce,describe
    bundles,duplicates=coalesce(state,release,region,bundles)
    all_frames=[f for f in all_frames if f.frame_id not in duplicates]
    key='source-union:'+digest([region.region_id,sorted(t.token_id for t in tokens)])
    for root,owned,label in bundles:
        root.semantic['composition_domain']={'decision_ref':key,'frame_refs':[f.frame_id for f in owned],
            'label':describe(state,root,owned)}
        for f in owned:f.semantic['structural_unresolved']=True
    if len(bundles)==1:
        for f in bundles[0][1]:f.semantic['structural_unresolved']=False
    elif not close_alternatives(state,region,all_frames):
        from .composition_children import select_child
        select_child(state,release,selector,region,all_frames,'ALL_SOURCE_PRODUCERS',
            'Which remaining interpretation fits the source? Preserve established roles, nominal functions, '
            'linked morphology and child scopes; decide only the remaining difference.')
    # Only the producer can discharge a diagnostic with an addressed proof.
    # Root cardinality says nothing about a failed probe or unfinished source.
    state.syntax_trace.append({'kind':'COMPOSITION_UNION_RESULT','region_ref':region.region_id,
        'root_refs':[f.frame_id for f in roots(all_frames)],
        'retained_diagnostics':[{'code':d.code,'detail':d.detail}
                                for d in state.diagnostics[diagnostics_before:]],
        'search_complete':False})
    return all_frames
