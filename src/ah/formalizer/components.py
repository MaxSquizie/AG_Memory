"""Orchestrate source-grounded clauses; substantive stages live in small modules."""
from .component_policy import policy
from .component_participants import prepare_implicit, resolve_implicit, add_memory_options


def compose(state, release, selector):
    """Build finite-clause alternatives including missing subject slots.

    Released conjunction and relative-event constructors compose local clauses;
    unsupported control/scope/adjuncts remain uncovered, not silently discarded.
    Existing complete SyntaxRules frames take priority
    as coverage, not as lexical winners over a newly guessed analysis.
    """
    cfg = policy(release)
    if not cfg:
        return
    state.require_structures_open('COMPONENT_COMPOSITION')
    evidence = {e.token_id:e for e in state.evidence}
    covered = {f.predicate_token_ref for f in state.frames if not f.semantic.get('structural_rejection')}
    from .regions import protected_intervals
    protected_ranges=protected_intervals(state.text)
    for region in list(state.region_forest.regions):
        if region.kind != 'SENTENCE':
            continue
        tokens = [evidence[t] for t in region.token_refs]
        predicates = [e for e in tokens if any(v.pos == 'VERB' and v.mood != 'imperative' for v in e.variants)]
        if cfg.get('quality_predicate_pos'):
            predicates += [e for e in tokens if e not in predicates and any(v.pos in cfg['quality_predicate_pos'] for v in e.variants)]
        compositional = bool(cfg.get('quality_predicate_pos') or cfg.get('modifier_content_role'))
        if not predicates or any(p.token_id in covered for p in predicates): continue
        if cfg.get('refinement'):
            from .component_refinement import compose_area
            from .soft_clause_boundaries import areas
            for area,owned in areas(state,release,selector,region,tokens,cfg):
                state.frames.extend(compose_area(state,release,selector,area,owned,cfg))
            continue
        from .component_area_scope import allowed, connectives
        if not allowed(state,release,region,tokens,conjunction=True):
            state.diag('COMPONENT_SCOPE_UNRESOLVED',region.region_id);continue
        if len(predicates)>1 and connectives(state,release,region,tokens):
            from .component_coordination import coordinate
            state.frames.extend(coordinate(state,release,selector,region,tokens,predicates,cfg,protected_ranges))
            continue
        if connectives(state,release,region,tokens):
            state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id);continue
        if not compositional and len(predicates) != 1: continue
        p = predicates[0]
        from .component_clause import build_clause
        if compositional:
            from .component_predication import compose_alternatives
            candidates=compose_alternatives(state,release,selector,region,tokens,predicates,cfg)
        else:
            candidates=build_clause(state,release,selector,region,tokens,p,cfg)
        state.frames.extend(candidates)
        state.syntax_trace.append({'composition_region':region.region_id,
            'candidates':[f.frame_id for f in candidates], 'coverage':'PARTIAL' if any(f.semantic['uncovered_token_refs'] or f.semantic['missing_required_roles'] for f in candidates) else 'COMPLETE'})
