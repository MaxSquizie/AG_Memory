"""Compose one finite clause inside a source region, with bounded alternatives."""
import re
from .component_probe import _probe
from .component_candidates import enumerate_candidates


def _build_clause(state,release,selector,region,tokens,p,cfg, *, select=True, attachment=None, nominal_groups=(), infinitive=None,qualitative_groups=(),proposition_slots=None,agreement_source=None,pending_roles=(),description_context=False,required_pending_roles=()):
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
    from .temporal_functions import owned_refs
    from .function_inventory import current
    current(state,'TEMPORAL',tokens,cfg.get('_task_constraints'),require=True)
    temporal = owned_refs(state,tokens)
    # The same released temporal ownership already excludes arguments below.
    # It must also exclude a predicate inside the time expression.
    from .nominal_reference_groups import owned_function_refs
    nominal_functions=owned_function_refs(state,tokens)
    if p.token_id in nominal_functions:
        state.syntax_trace.append({'kind':'NOMINAL_FUNCTION_PREDICATE_EXCLUDED','region_ref':region.region_id,
            'predicate_ref':p.token_id})
        return []
    if p.token_id in temporal:
        state.syntax_trace.append({'kind':'TEMPORAL_PREDICATE_EXCLUDED','region_ref':region.region_id,
            'source_range':list(region.source_range),'predicate_ref':p.token_id,
            'temporal_refs':sorted(temporal)})
        return []
    from .component_phrases import prepositional_groups
    groups=prepositional_groups(tokens,temporal,state=state,constraints=cfg.get('_task_constraints'))
    prep_markers={r for g in groups.values() for r in g.get('function_refs',[g['token_ref']])}
    allowed_cases=set(cfg['open_case_roles']) | {c for val in release.entries('R-V') for role in val['roles'] for c in role.get('allowed_cases',())}
    if attachment:
        allowed_cases.update(c for rule in cfg['refinement']['participle_voices'] for c in rule['case_roles'])
    if cfg.get('dependency_reduction'):
        allowed_cases.update({'gen','nom'})  # nominal dependencies need not fill a predicate role
    nominal_connectors={t for g in nominal_groups for t in g['marker_refs']}
    quantity_markers={t for g in qualitative_groups for t in g.get('quantity_token_refs',[g['marker_ref']]) if t!=g['head_ref']}
    nominals = [e for e in tokens if e.token_id not in temporal|prep_markers|nominal_connectors|quantity_markers and e != p and e.token_id not in nominal_functions
                and (e.token_id in groups or any(v.pos in {'NOUN','NPRO'} and (set(v.cases)&allowed_cases or v.origin=='CONTEXTUAL' and not v.cases) for v in e.variants))]
    # The number of nominals is not a grammatical exclusion. Large domains
    # go through constraint reduction, under the same released search budget.
    candidates=enumerate_candidates(state,release,cfg,region,tokens,p,temporal,nominals,groups,selector=selector,attachment=attachment,nominal_groups=nominal_groups,infinitive=infinitive,proposition_slots=proposition_slots,agreement_source=agreement_source,pending_roles=pending_roles,qualitative_groups=qualitative_groups,description_context=description_context,required_pending_roles=required_pending_roles)
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
        from .probe_wording import role as role_text, linked_readings
        for f in candidates:
            roles=', '.join(role_text(r)+'=«'+evidence[t].span+'» at '+str(evidence[t].start) for t,r in f.semantic['proposed_roles'].items())
            if f.semantic['relative_temporal']: roles += '; relative event anchors='+str(f.semantic['relative_temporal'])
            if f.semantic['preposition_bindings']:
                roles+='; relational markers: '+ '; '.join('«'+evidence[b['token_ref']].span+'» at '+str(evidence[b['token_ref']].start)+
                    ' introduces «'+evidence[t].span+'» at '+str(evidence[t].start) for t,b in f.semantic['preposition_bindings'].items())
            if f.semantic['missing_required_roles']: roles += '; UNRESOLVED mandatory roles='+', '.join(role_text(r) for r in f.semantic['missing_required_roles'])
            if f.semantic.get('implicit_arguments'): roles += '; omitted roles (identity unresolved)='+', '.join(role_text(r) for r in f.semantic['implicit_arguments'])
            options.append({'candidate_id':f.frame_id,'label':'Predicate «'+p.span+'» at '+str(p.start)+'; '+roles+
                            '; whole readings: '+linked_readings(f.semantic['morph_bindings'],evidence)})
        if len(raw)>cfg['context_chars'] or all(f.semantic['structural_unresolved'] for f in candidates):
            chosen=None
        else:
            chosen=_probe(state,selector,release,region.region_id+'|composition','component_attachment',options,raw,region.source_range,
                question='Which proposed clause reading fits this source? Preserve the shown whole morphological readings and role assignments within each alternative; do not assert that its event occurred.', target_refs=(p.token_id,))
        for f in candidates:
            f.semantic['composition_decision']=region.region_id+'|composition'
            if f.frame_id!=chosen: f.semantic['structural_unresolved']=True
    return candidates


def build_clause(state,release,selector,region,tokens,p,cfg,**kwargs):
    from .function_inventory import InventoryUnavailable,attach
    try:
        frames=_build_clause(state,release,selector,region,tokens,p,cfg,**kwargs)
        return attach(state,tokens,cfg,frames)
    except InventoryUnavailable as exc:
        state.diag('FUNCTION_INVENTORY_UNRESOLVED',str(exc))
        return []
