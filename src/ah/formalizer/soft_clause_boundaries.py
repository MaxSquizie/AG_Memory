"""Internal capitalized finite verbs propose, never establish, a clause boundary."""
from .canonical_ledger import digest
from .component_probe import _probe
from .regions import TextRegion


def areas(state,release,selector,region,tokens,cfg):
    if cfg.get('soft_clause_boundaries')!='CAPITAL_FINITE_HINT_V1':return [(region,tokens)]
    from .component_area_scope import allowed
    if not allowed(state,release,region,tokens,conjunction=True):return [(region,tokens)]
    finite=lambda t:any(v.pos=='VERB' and v.mood!='imperative' for v in t.variants)
    proper=lambda t:any(v.features & {'Name','Surn','Patr','Geox','Orgn','Trad'} for v in t.variants)
    proposals=[i for i,t in enumerate(tokens) if i and t.span[:1].isupper() and
               finite(t) and not proper(t) and any(finite(p) for p in tokens[:i])]
    if not proposals:return [(region,tokens)]
    if len(proposals)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
        state.diag('COMPONENT_BOUNDARY_SEARCH_INCOMPLETE',region.region_id)
        return [(region,tokens)]
    selected=[]
    for i in proposals:
        t=tokens[i];key=region.region_id+'|soft-boundary:'+t.token_id
        chosen=_probe(state,selector,release,key,'clause_boundary',[
            {'candidate_id':'SPLIT','label':'A new independent clause begins at «'+t.span+'»; it is outside any preceding relative description'},
            {'candidate_id':'KEEP','label':'This predicate remains in the existing clause/scope; do not split here'}],
            state.text[slice(*region.source_range)],region.source_range,
            question='Check grammar and scope on BOTH sides. Internal capitalization of a possible finite verb is only a weak clue, '
            'not proof of a missing period. A name, heading, coordinated predicate or quoted content is not automatically a new clause. '
            'Select SPLIT only when the context supports an independent clause; otherwise KEEP or ?.')
        state.syntax_trace.append({'kind':'SOFT_CLAUSE_BOUNDARY','decision_ref':key,
            'token_ref':t.token_id,'cue':'CAPITAL_FINITE_NONPROPER','selected':chosen})
        if chosen=='SPLIT':selected.append(i)
    if not selected:return [(region,tokens)]
    out=[]
    for a,b in zip([0,*selected],[*selected,len(tokens)]):
        part=tokens[a:b]
        child=TextRegion('region:'+digest([region.region_id,'SOFT_BOUNDARY',[t.token_id for t in part]]),
            'CLAUSE',(part[0].start,part[-1].end),tuple(t.token_id for t in part),region.region_id,
            grounds=('CLOSED_BOUNDARY_SELECTION',))
        state.region_forest.regions.append(child);out.append((child,part))
    return out
