"""Carry established local attachments into the remaining composition question."""


def question(state,region):
    evidence={e.token_id:e for e in state.evidence};rows=[]
    choices=state.observation.get('clarification_choices',{})
    for trace in state.syntax_trace:
        if trace.get('kind')!='NOMINAL_HOST_QUESTION' or trace['region_ref']!=region.region_id or not trace['selected']:continue
        view=next(v for v in trace['candidate_subtrees'] if v['candidate_id']==trace['selected'])
        phrase=' '.join(evidence[t].span for t in trace['phrase_refs'])
        origin='explicit user clarification' if trace.get('decision_ref') in choices else 'previous resolved local question'
        rows.append('«'+phrase+'» attaches to «'+view['surface']+'» ('+origin+')')
    for e in state.evidence:
        if e.lexical_recovery and region.source_range[0]<=e.start and e.end<=region.source_range[1]:
            rows.append('explicitly selected inflection reading «'+e.span+'» → «'+e.lexical_recovery['surface']+'»; source text unchanged')
    if not rows:return ''
    return 'Already established interpretation constraints: '+'; '.join(rows)+'. Evaluate the remaining composition subject to these constraints; do not ask again which of those already selected hosts was intended. These constraints do not assert world facts. '
