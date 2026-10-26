"""Exclude questions whose candidate branch was explicitly rejected."""


def rejected_refs(trace):
    return {row['decision_ref'] for row in trace
            if row.get('kind')=='DEPENDENCY_REJECTED' and row.get('decision_ref')}


def page_refs(trace):
    """Pages belong to a domain even when enumeration stopped before closure."""
    refs={row['decision_ref'] for row in trace
          if row.get('decision_ref') and (row.get('kind')=='PROBE_PAGE' or
          row.get('kind')=='STRUCTURAL_TASK' and (row.get('selection_provisional') or 'page' in row))}
    for row in trace:
        if row.get('kind')=='TASK_DOMAIN':refs.update(row.get('page_refs',()))
    return refs


def obsolete_reason(request):
    trace=request.get('generation_snapshot',{}).get('syntax_trace',[])
    records=request.get('generation_snapshot',{}).get('component_probe_records',{})
    if request.get('decision_ref') in page_refs(trace) or request.get('decision_ref') in records:
        return 'CLARIFICATION_PAGE_NOT_ADMISSIBLE'
    if request.get('decision_ref') in rejected_refs(trace):
        return 'CLARIFICATION_BRANCH_REJECTED'
    return None


def obsolete(request):
    return obsolete_reason(request) is not None


def prune(state):
    rejected=rejected_refs(state.syntax_trace) | page_refs(state.syntax_trace) | set(state.component_probe_records)
    state.clarification_candidates=[row for row in state.clarification_candidates
                                    if row['decision_ref'] not in rejected]
