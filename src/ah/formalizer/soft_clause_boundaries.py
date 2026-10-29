"""Closed scope choices over weak morphological boundary proposals."""
from .canonical_ledger import digest
from .component_probe import _probe
from .regions import TextRegion


def areas(state,release,selector,region,tokens,cfg):
    version=cfg.get('soft_clause_boundaries')
    if version not in {'CAPITAL_FINITE_HINT_V1','FINITE_SUBJECT_HINT_V2'}:return [(region,tokens)]
    from .component_area_scope import allowed
    if not allowed(state,release,region,tokens,conjunction=True):return [(region,tokens)]
    # A possible released proposition slot must reach the recursive composer
    # intact. A weak subject boundary cannot assert its content independently.
    from .attitude_composition import complement_options
    if complement_options(state,release,tokens,None,1):
        state.syntax_trace.append({'kind':'DEFERRED_CLAUSE_BOUNDARY',
            'region_ref':region.region_id,'reason':'RELEASED_PROPOSITION_SCOPE'})
        return [(region,tokens)]
    finite=lambda t:any(v.pos=='VERB' and v.mood!='imperative' for v in t.variants)
    proper=lambda t:any(v.features & {'Name','Surn','Patr','Geox','Orgn','Trad'} for v in t.variants)
    proposals={i:'CAPITAL_FINITE_NONPROPER' for i,t in enumerate(tokens) if i and t.span[:1].isupper() and
               finite(t) and not proper(t) and any(finite(p) for p in tokens[:i])}
    if version=='FINITE_SUBJECT_HINT_V2':
        from .clause_boundary_candidates import subject_starts
        for i in subject_starts(state,release,region,tokens,cfg):
            proposals[i]='FINITE_WITH_EXPLICIT_SUBJECT'
    if not proposals:return [(region,tokens)]
    if len(proposals)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
        state.diag('COMPONENT_BOUNDARY_SEARCH_INCOMPLETE',region.region_id)
        return [] if version=='FINITE_SUBJECT_HINT_V2' else [(region,tokens)]
    selected=[]
    for i in sorted(proposals):
        t=tokens[i];key=region.region_id+'|soft-boundary:'+t.token_id
        chosen=_probe(state,selector,release,key,'clause_boundary',[
            {'candidate_id':'SPLIT','label':'Independent clauses at this boundary: LEFT «'+state.text[tokens[0].start:t.start]+'» / RIGHT «'+state.text[t.start:tokens[-1].end]+'»; the right clause is outside preceding descriptions'},
            {'candidate_id':'KEEP','label':'This predicate remains in the existing clause/scope; do not split here'}],
            state.text[slice(*region.source_range)],region.source_range,
            question='Check grammar and scope on BOTH sides. Separate finite verbs with a compatible subject, punctuation and capitalization are only weak clues. '
            'A name, heading, coordinated predicate or quoted content is not automatically a new clause. '
            'Select SPLIT only when the context supports an independent clause; otherwise KEEP or ?.', target_refs=(t.token_id,))
        state.syntax_trace.append({'kind':'SOFT_CLAUSE_BOUNDARY','decision_ref':key,
            'token_ref':t.token_id,'cue':proposals[i],'selected':chosen})
        if chosen is None and version=='FINITE_SUBJECT_HINT_V2':
            state.diag('COMPONENT_BOUNDARY_UNRESOLVED',region.region_id)
            return []
        if chosen=='SPLIT':selected.append(i)
    if not selected:return [(region,tokens)]
    parts=[tokens[a:b] for a,b in zip([0,*selected],[*selected,len(tokens)])]
    separators=[]
    if version=='FINITE_SUBJECT_HINT_V2':
        # Only a confirmed boundary licenses consuming its separator. Internal
        # punctuation and every source token remain recorded in the parent.
        for part in parts[:-1]:
            if part and part[-1].span in {',',';'}:
                separators.append(part.pop().token_id)
    if version=='FINITE_SUBJECT_HINT_V2' and any(not any(finite(t) for t in part) for part in parts):
        state.diag('COMPONENT_BOUNDARY_UNRESOLVED',region.region_id)
        return []
    state.syntax_trace.append({'kind':'SELECTED_CLAUSE_PARTITION','parent_ref':region.region_id,
        'parts':[[t.token_id for t in part] for part in parts],'separator_refs':separators})
    out=[]
    for part in parts:
        child=TextRegion('region:'+digest([region.region_id,'SOFT_BOUNDARY',[t.token_id for t in part]]),
            'CLAUSE',(part[0].start,part[-1].end),tuple(t.token_id for t in part),region.region_id,
            grounds=('CLOSED_BOUNDARY_SELECTION',))
        state.region_forest.regions.append(child);out.append((child,part))
    return out
