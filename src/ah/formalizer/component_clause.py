"""Compose one finite clause inside a source region, with bounded alternatives."""
import re
from .component_probe import _probe
from .component_candidates import enumerate_candidates


def build_clause(state,release,selector,region,tokens,p,cfg, *, select=True, attachment=None, nominal_groups=(), infinitive=None,qualitative_groups=(),proposition_slots=None,agreement_source=None,pending_roles=()):
    from .contextual_name_case import overlay
    tokens=overlay(tokens,nominal_groups)
    if select:
        from .contextual_preposition_case import overlay as governed_readings
        tokens=governed_readings(state,release,selector,region,tokens,cfg)
        if tokens is None:return []
    evidence={e.token_id:e for e in tokens}
    from .component_source import view
    raw=view(state,region,tokens)
    # Relative event anchors are typed children of the common composer.
    # This layer owns only lexical calendar/clock expressions.
    temporal = set()
    for rule in release.entries('TemporalRules'):
        for m in re.finditer(rule['pattern'],raw,re.I):
            from .clock_ranges import boundary_spans
            for a,b in boundary_spans(rule,m):
                lo,hi = region.source_range[0]+a,region.source_range[0]+b
                temporal.update(e.token_id for e in tokens if lo <= e.start and e.end <= hi)
    from .component_phrases import prepositional_groups
    groups=prepositional_groups(tokens,temporal)
    prep_markers={g['token_ref'] for g in groups.values()}
    allowed_cases=set(cfg['open_case_roles']) | {c for val in release.entries('R-V') for role in val['roles'] for c in role.get('allowed_cases',())}
    if attachment:
        allowed_cases.update(c for rule in cfg['refinement']['participle_voices'] for c in rule['case_roles'])
    if cfg.get('dependency_reduction'):
        allowed_cases.update({'gen','nom'})  # nominal dependencies need not fill a predicate role
    nominal_connectors={t for g in nominal_groups for t in g['marker_refs']}
    quantity_markers={t for g in qualitative_groups for t in g.get('quantity_token_refs',[g['marker_ref']])}
    nominals = [e for e in tokens if e.token_id not in temporal|prep_markers|nominal_connectors|quantity_markers and e != p
                and (e.token_id in groups or any(v.pos in {'NOUN','NPRO'} and set(v.cases)&allowed_cases for v in e.variants))]
    # The number of nominals is not a grammatical exclusion. Large domains
    # go through constraint reduction, under the same released search budget.
    candidates=enumerate_candidates(state,release,cfg,region,tokens,p,temporal,nominals,groups,selector=selector,attachment=attachment,nominal_groups=nominal_groups,infinitive=infinitive,proposition_slots=proposition_slots,agreement_source=agreement_source,pending_roles=pending_roles,qualitative_groups=qualitative_groups)
    for f in candidates:
        from .nominal_readings import attach_groups
        attach_groups(f,qualitative_groups)
        f.semantic['relative_temporal']=[]  # legacy reader field, no new producer
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
            if f.semantic.get('implicit_arguments'): roles += '; omitted roles (identity unresolved)='+str(list(f.semantic['implicit_arguments']))
            options.append({'candidate_id':f.frame_id,'label':str(f.semantic['morph_bindings'][p.token_id]['lemma'])+'; '+roles+'; morphology='+str({t:{k:v for k,v in m.items() if k in {'cases','number','gender','pos'}} for t,m in f.semantic['morph_bindings'].items()})})
        if len(raw)>cfg['context_chars'] or all(f.semantic['structural_unresolved'] for f in candidates):
            chosen=None
        else:
            chosen=_probe(state,selector,release,region.region_id+'|composition','component_attachment',options,raw,region.source_range)
        for f in candidates:
            f.semantic['composition_decision']=region.region_id+'|composition'
            if f.frame_id!=chosen: f.semantic['structural_unresolved']=True
    return candidates
