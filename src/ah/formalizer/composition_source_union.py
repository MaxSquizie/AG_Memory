"""Every applicable producer runs before the common child domain is closed."""
from .canonical_ledger import digest
from .composition_tree import roots


def merge(state,release,selector,region,tokens,cfg,grammar,components,diagnostics_before):
    grammar=list(grammar or ());components=list(components)
    state.syntax_trace.append({'kind':'COMPOSITION_PRODUCERS','region_ref':region.region_id,
        'source_range':list(region.source_range),'sources':[
            {'source':'GRAMMAR','frames':len(grammar)}, {'source':'COMPONENT','frames':len(components)}],
        'partial_diagnostics':[d.code for d in state.diagnostics[diagnostics_before:]]})
    if not grammar:return components
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
    # Reaching a generator limit is not a negative result for that generator.
    local=state.diagnostics[diagnostics_before:]
    if any('SEARCH_INCOMPLETE' in d.code or d.code=='COMPONENT_PROBE_FAILED' for d in local):
        for f in all_frames:f.semantic['structural_unresolved']=True
        return all_frames
    if not roots(components) and not any(f.semantic.get('composition_domain') for f in components) and any(
            'UNRESOLVED' in d.code for d in local):
        for f in all_frames:f.semantic['structural_unresolved']=True
        state.diag('COMPOSITION_PRODUCER_PENDING',region.region_id)
        return all_frames
    if not bundles:return all_frames
    from .composition_equivalence import coalesce,describe
    bundles,duplicates=coalesce(state,release,region,bundles)
    all_frames=[f for f in all_frames if f.frame_id not in duplicates]
    key='source-union:'+digest([region.region_id,sorted(t.token_id for t in tokens)])
    for root,owned,label in bundles:
        source=root.semantic.get('composition_source','COMPONENT')
        root.semantic['composition_domain']={'decision_ref':key,'frame_refs':[f.frame_id for f in owned],
            'label':source+': '+describe(state,root,owned)}
        for f in owned:f.semantic['structural_unresolved']=True
    if len(bundles)==1:
        for f in bundles[0][1]:f.semantic['structural_unresolved']=False
    else:
        from .composition_children import select_child
        select_child(state,release,selector,region,all_frames,'ALL_SOURCE_PRODUCERS',
            'Compare complete alternatives from ALL applicable producers. A grammar match does not suppress '
            'component alternatives. Preserve whole linked morphology, source coverage, roles and scopes.')
    # Local dead ends belong to a producer trace, not to the accepted alternative.
    if roots(all_frames):del state.diagnostics[diagnostics_before:]
    return all_frames
