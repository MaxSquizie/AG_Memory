"""Explicit nominal conjunctions occupy one slot without equating members."""
from .canonical_ledger import digest
from .component_probe import _probe
from .component_area_scope import connectives


def intersect_cases(domains):
    """None is unknown; an empty set is a proved conflict of known domains."""
    known=[set(d) for d in domains if d is not None]
    return set.intersection(*known) if known else None


def candidate_cases(variants):
    # role_choices admits only CONTEXTUAL unknown-case readings. Preserve that
    # same possibility here without changing the reading or inventing a case.
    if any(not v.cases and v.origin=='CONTEXTUAL' for v in variants):return None
    return {c for v in variants for c in v.cases}


def compatible_cases(readings, group_cases=None):
    domains=[group_cases]
    for reading in readings:
        cases=reading['cases'] if isinstance(reading,dict) else reading.cases
        origin=reading.get('origin') if isinstance(reading,dict) else reading.origin
        if not cases and origin!='CONTEXTUAL':return False
        domains.append(set(cases) if cases else None)
    result=intersect_cases(domains)
    return result is None or bool(result)


def merge_groups(groups):
    """Connected source membership is transitive, regardless of edge order."""
    from copy import deepcopy
    merged=[]
    for original in groups:
        group=deepcopy(original)
        # Consume all connected components, including those reached by a bridge.
        while True:
            linked=next((old for old in merged if set(old['member_refs']) & set(group['member_refs'])),None)
            if linked is None:break
            merged.remove(linked)
            group['member_refs']=list(dict.fromkeys([*linked['member_refs'],*group['member_refs']]))
            group['marker_refs']=list(dict.fromkeys([*linked['marker_refs'],*group['marker_refs']]))
            group['contextual_readings']=[*linked.get('contextual_readings',()),*group.get('contextual_readings',())]
            cases=intersect_cases([linked['cases'],group['cases']])
            if cases is not None and not cases:return None
            group['cases']=sorted(cases) if cases is not None else None
        merged.append(group)
    return merged


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
        cases=intersect_cases([candidate_cases(av),candidate_cases(bv)])
        contextual=[]
        if cases is not None and not cases and av and bv:
            from .contextual_name_case import resolve
            rows=resolve(state,release,selector,region,a,b,cfg)
            if rows:
                contextual.extend(rows)
                cases=sorted({c for row in rows for v in row['variants'] for c in v['cases']})
        if cases is not None and not cases:
            if av and bv:
                state.diag('NOMINAL_COORDINATION_CASE_CONFLICT',region.region_id)
                return False
            return None
        groups.append({'member_refs':[a.token_id,b.token_id],
            'marker_refs':[t.token_id for t in tokens if lo<=t.start and t.end<=hi],
            'cases':sorted(cases) if cases is not None else None,'operator':'AND','contextual_readings':contextual})
    # Overlapping pairs form one connected nominal group, never two copies.
    merged=merge_groups(groups)
    if merged is None:return None
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
        'Do not infer that the members are one entity or that an event happened. Case and role are resolved later.', target_refs=tuple(t.token_id for t in tokens if any(t.token_id in g['member_refs'] or t.token_id in g['marker_refs'] for g in merged)))
    state.syntax_trace.append({'kind':'NOMINAL_COORDINATION','region_ref':region.region_id,
        'decision_ref':key,'groups':merged,'selected':chosen,
        'task_outcome':'NOT_APPLICABLE' if chosen=='OTHER' else 'SUPPORTED' if chosen=='NOMINAL' else 'PENDING'})
    # Explicitly rejecting this grouping is not an unknown or failed probe.
    # The next producer must establish its own relation before composing it.
    if chosen=='OTHER':return None
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
