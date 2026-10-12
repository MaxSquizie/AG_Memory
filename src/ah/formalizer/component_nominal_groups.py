"""Explicit nominal conjunctions occupy one slot without equating members."""
from .canonical_ledger import digest
from .component_probe import _probe
from .component_area_scope import connectives


def select(state, release, selector, region, tokens, cfg):
    spans=connectives(state,release,region,tokens)
    if not spans: return []
    groups=[]
    for lo,hi in spans:
        before=[t for t in tokens if t.end<=lo];after=[t for t in tokens if t.start>=hi]
        if not before or not after: return None
        a,b=before[-1],after[0]
        av=[v for v in a.variants if v.pos in {'NOUN','NPRO'}]
        bv=[v for v in b.variants if v.pos in {'NOUN','NPRO'}]
        cases=sorted({c for x in av for y in bv for c in x.cases & y.cases})
        contextual=[]
        if not cases and av and bv:
            from .contextual_name_case import resolve
            row=resolve(state,release,selector,region,a,b,cfg)
            if row:
                contextual.append(row)
                cases=sorted({c for v in row['variants'] for c in v['cases']})
        if not cases:
            if av and bv:
                state.diag('NOMINAL_COORDINATION_CASE_CONFLICT',region.region_id)
                return False
            return None
        groups.append({'member_refs':[a.token_id,b.token_id],
            'marker_refs':[t.token_id for t in tokens if lo<=t.start and t.end<=hi],
            'cases':cases,'operator':'AND','contextual_readings':contextual})
    # Overlapping pairs form one connected nominal group, never two copies.
    merged=[]
    for g in groups:
        old=next((p for p in merged if set(p['member_refs']) & set(g['member_refs'])),None)
        if old:
            old['member_refs']=list(dict.fromkeys([*old['member_refs'],*g['member_refs']]))
            old['contextual_readings']+=g['contextual_readings']
            old['marker_refs']+=g['marker_refs'];old['cases']=sorted(set(old['cases']) & set(g['cases']))
            if not old['cases']: return None
        else:merged.append(g)
    if len(merged)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
        return False
    key=region.region_id+'|nominal-coordination:'+digest(merged)
    evidence={t.token_id:t for t in tokens}
    labels=[' + '.join('«'+evidence[t].span+'»' for t in g['member_refs']) for g in merged]
    chosen=_probe(state,selector,release,key,'nominal_coordination',[
        {'candidate_id':'NOMINAL','label':'Conjoined participants in ONE nominal slot: '+'; '.join(labels)},
        {'candidate_id':'OTHER','label':'The connector has another scope; these nominal groups are not established'}],
        state.text[slice(*region.source_range)],region.source_range,
        question='Which units does the written conjunction connect in this area? '
        'Do not infer that the members are one entity or that an event happened. Case and role are resolved later.')
    state.syntax_trace.append({'kind':'NOMINAL_COORDINATION','region_ref':region.region_id,
        'decision_ref':key,'groups':merged,'selected':chosen})
    return merged if chosen=='NOMINAL' else False


def valid_roles(mapping, groups):
    """Duplicate slot assignments need a whole selected group, not proximity."""
    for g in groups:
        assigned=[mapping.get(t) for t in g['member_refs']]
        if None in assigned or len(set(assigned))!=1:return False
    for role in set(mapping.values()):
        members={t for t,r in mapping.items() if r==role}
        if len(members)>1 and not any(members==set(g['member_refs']) for g in groups):return False
    return True


def group_for(frame, role, selected_roles):
    members={t for t,r in selected_roles.items() if r==role}
    matches=[g for g in frame.semantic.get('nominal_groups',()) if set(g['member_refs'])==members]
    if len(matches)!=1: raise ValueError('ARGUMENT_CARDINALITY_UNRESOLVED')
    return matches[0]
