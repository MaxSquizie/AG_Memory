"""Exclude questions whose candidate branch was explicitly rejected."""


def rejected_refs(trace):
    return {row['decision_ref'] for row in trace
            if row.get('kind')=='DEPENDENCY_REJECTED' and row.get('decision_ref')}


def obsolete(request):
    trace=request.get('generation_snapshot',{}).get('syntax_trace',[])
    return request.get('decision_ref') in rejected_refs(trace)


def prune(state):
    rejected=rejected_refs(state.syntax_trace)
    state.clarification_candidates=[row for row in state.clarification_candidates
                                    if row['decision_ref'] not in rejected]
