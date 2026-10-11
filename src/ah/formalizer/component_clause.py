"""Compose one finite clause inside a source region, with bounded alternatives."""
import re
from .component_probe import _probe
from .component_candidates import enumerate_candidates


def build_clause(state,release,selector,region,tokens,p,cfg, *, select=True):
    evidence={e.token_id:e for e in tokens}
    raw=state.text[slice(*region.source_range)]
    from .component_temporal import relative_adjuncts, questions
    relative=relative_adjuncts(state,release,region,tokens)
    temporal = {tid for row in relative for tid in row['anchor_refs']}
    for rule in release.entries('TemporalRules'):
        for m in re.finditer(rule['pattern'],raw,re.I):
            lo,hi = region.source_range[0]+m.start(),region.source_range[0]+m.end()
            temporal.update(e.token_id for e in tokens if lo <= e.start and e.end <= hi)
    from .component_phrases import prepositional_groups
    groups=prepositional_groups(tokens,temporal)
    prep_markers={g['token_ref'] for g in groups.values()}
    allowed_cases=set(cfg['open_case_roles']) | {c for val in release.entries('R-V') for role in val['roles'] for c in role.get('allowed_cases',())}
    nominals = [e for e in tokens if e.token_id not in temporal|prep_markers and e != p
                and (e.token_id in groups or any(v.pos in {'NOUN','NPRO'} and set(v.cases)&allowed_cases for v in e.variants))]
    # No arbitrary truncation of the argument candidate inventory.
    if len(nominals) > 3:
        state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
        return []
    candidates=enumerate_candidates(state,release,cfg,region,tokens,p,temporal,nominals,groups)
    for f in candidates:
        f.semantic['relative_temporal']=relative
        f.semantic['component_questions'].extend(questions(relative))
        if relative: f.semantic['requires_attachment_probe']=True
    if not select: return candidates
    if not candidates: return []
    if len(candidates)>cfg['max_candidates']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
        for f in candidates: f.semantic['structural_unresolved']=True
    elif len(candidates)>1 or any(f.semantic['requires_attachment_probe'] for f in candidates):
        options=[]
        for f in candidates:
            roles=', '.join(r+'='+evidence[t].span for t,r in f.semantic['proposed_roles'].items())
            if f.semantic['relative_temporal']: roles += '; relative event anchors='+str(f.semantic['relative_temporal'])
            if f.semantic['preposition_bindings']: roles += '; prepositions='+str(f.semantic['preposition_bindings'])
            if f.semantic['missing_required_roles']: roles += '; UNRESOLVED mandatory roles='+str(f.semantic['missing_required_roles'])
            if f.semantic.get('implicit_arguments'): roles += '; subject omitted (identity unresolved)'
            options.append({'candidate_id':f.frame_id,'label':str(f.semantic['morph_bindings'][p.token_id]['lemma'])+'; '+roles+'; morphology='+str({t:{k:v for k,v in m.items() if k in {'cases','number','gender','pos'}} for t,m in f.semantic['morph_bindings'].items()})})
        if len(raw)>cfg['context_chars'] or all(f.semantic['structural_unresolved'] for f in candidates):
            chosen=None
        else:
            chosen=_probe(state,selector,release,region.region_id+'|composition','component_attachment',options,raw,region.source_range)
        for f in candidates:
            f.semantic['composition_decision']=region.region_id+'|composition'
            if f.frame_id!=chosen: f.semantic['structural_unresolved']=True
    return candidates
