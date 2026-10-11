"""Orchestrate source-grounded clauses; substantive stages live in small modules."""
import re
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
        # A multi-predicate region needs a licensed attachment/coordination.
        if len(predicates)>1 and (not compositional or any(
                r.get('operator') == 'AND' and re.search(r['pattern'],state.text[slice(*region.source_range)],re.I)
                for r in release.entries('ScopeLexicon'))) and not any(p.token_id in covered for p in predicates):
            from .component_coordination import coordinate
            coordinate(state,release,selector,region,tokens,predicates,cfg,protected_ranges)
            continue
        if not predicates or any(p.token_id in covered for p in predicates): continue
        if not compositional and len(predicates) != 1: continue
        p = predicates[0]
        raw = state.text[region.source_range[0]:region.source_range[1]]
        # Never flatten a scoped region into an asserted finite clause.
        protected = any(lo <= q.start < hi for q in predicates for lo,hi in protected_ranges)
        from .component_temporal import relative_adjuncts
        relative=relative_adjuncts(state,release,region,tokens)
        allowed={(row['resource_pattern'],row['operator']) for row in relative}
        from .clock_ranges import consumed_scope_spans, scope_consumed
        clock_spans=consumed_scope_spans(raw,state.observation,release)
        scope = protected or any((r['pattern'],r.get('operator')) not in allowed and
            not scope_consumed(r,m,clock_spans) for r in release.entries('ScopeLexicon')
            for m in re.finditer(r['pattern'],raw,re.I))
        scope |= any(e.span in {'«','»','"','(',')','?',':'} for e in tokens)
        if scope:
            state.diag('COMPONENT_SCOPE_UNRESOLVED', region.region_id)
            continue
        if cfg.get('refinement'):
            from .refinement_boundaries import starts
            if any(starts(tokens,cfg['refinement'])):
                from .component_refinement import compose_area
                state.frames.extend(compose_area(state,release,selector,region,tokens,cfg))
                continue
        from .component_clause import build_clause
        if compositional:
            from .component_predication import compose_alternatives
            candidates=compose_alternatives(state,release,selector,region,tokens,predicates,cfg)
        else:
            candidates=build_clause(state,release,selector,region,tokens,p,cfg)
        state.frames.extend(candidates)
        state.syntax_trace.append({'composition_region':region.region_id,
            'candidates':[f.frame_id for f in candidates], 'coverage':'PARTIAL' if any(f.semantic['uncovered_token_refs'] or f.semantic['missing_required_roles'] for f in candidates) else 'COMPLETE'})
