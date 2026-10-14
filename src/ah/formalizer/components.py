"""Orchestrate source-grounded clauses; substantive stages live in small modules."""
from .component_policy import policy
from .component_participants import prepare_implicit, resolve_implicit, add_memory_options


def compose(state, release, selector, context_reader=None):
    from .composition_session import session
    with session(state,release,context_reader):
        _compose(state,release,selector)


def _compose(state, release, selector):
    """Build finite-clause alternatives including missing subject slots.

    Released conjunction and relative-event constructors compose local clauses;
    unsupported control/scope/adjuncts remain uncovered, not silently discarded.
    The general task profile combines all producers. Legacy profiles retain
    their released grammar-first coverage policy.
    """
    cfg = policy(release)
    if not cfg:
        return
    if state.grammar_search_incomplete:
        state.diag('COMPONENT_SEARCH_INCOMPLETE','released grammar enumeration incomplete')
        state.syntax_trace.append({'kind':'STRUCTURAL_TASK','slot':'structural_relation',
            'status':'BLOCKED','reason':'GRAMMAR_SEARCH_LIMIT','examined':0,
            'source_range':[0,len(state.text)]})
        return
    state.require_structures_open('COMPONENT_COMPOSITION')
    evidence = {e.token_id:e for e in state.evidence}
    from .component_refinement import compose_area
    from .soft_clause_boundaries import areas
    from .composition_session import current
    inventory=current(state).sources
    from .structural_tasks import enabled
    joint=enabled(release)
    from bisect import bisect_left
    grammar_frames=sorted(state.frames,key=lambda f:f.source_range[0])
    starts=[f.source_range[0] for f in grammar_frames]
    for region in list(state.region_forest.regions):
        if region.kind != 'SENTENCE':continue
        tokens = [evidence[t] for t in region.token_refs]
        existing=[f for f in grammar_frames[bisect_left(starts,region.source_range[0]):bisect_left(starts,region.source_range[1])]
                  if not f.semantic.get('structural_rejection') and f.source_range[1]<=region.source_range[1]]
        if inventory.complete(tokens) and not joint:continue
        generated=[]
        for area,owned in ([(region,tokens)] if joint else areas(state,release,selector,region,tokens,cfg)):
            from .composition_tree import finalize
            children=compose_area(state,release,selector,area,owned,cfg)
            finalize(state,area,children)
            generated.extend(children)
        if existing:
            # Partial grammar candidates stay addressable; an overlapping
            # incomplete interpretation must not assert an independent fragment.
            for frame in existing:
                frame.semantic['structural_unresolved']=True
                frame.semantic['structural_rejection']='INCOMPLETE_REGION_COVERAGE'
            from .composition_tree import internalize
            internalize(existing)
            state.syntax_trace.append({'kind':'REGION_COVERAGE_REFINEMENT','region_ref':region.region_id,
                'previous_frame_refs':[f.frame_id for f in existing],
                'candidate_refs':[f.frame_id for f in generated]})
        state.frames.extend(generated)
