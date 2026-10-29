"""Carry established local attachments into the remaining composition question."""


def question(state,region):
    evidence={e.token_id:e for e in state.evidence};rows=[]
    from .composition_session import current
    runtime=current(state);scope=runtime.input_signature() if runtime else None
    choices=state.observation.get('clarification_choices',{})
    for trace in state.syntax_trace:
        if trace.get('kind')!='NOMINAL_HOST_QUESTION' or trace['region_ref']!=region.region_id or not trace['selected']:continue
        if trace.get('task_scope')!=scope or not host_live(state,trace):continue
        view=next(v for v in trace['candidate_subtrees'] if v['candidate_id']==trace['selected'])
        phrase=' '.join(evidence[t].span for t in trace['phrase_refs'])
        origin='explicit user clarification' if trace.get('decision_ref') in choices else 'previous resolved local question'
        rows.append('«'+phrase+'» attaches to «'+view['surface']+'» ('+origin+')')
    for e in state.evidence:
        if e.lexical_recovery and region.source_range[0]<=e.start and e.end<=region.source_range[1]:
            rows.append('explicitly selected inflection reading «'+e.span+'» → «'+e.lexical_recovery['surface']+'»; source text unchanged')
    if not rows:return ''
    return 'Already established interpretation constraints: '+'; '.join(rows)+'. Evaluate the remaining composition subject to these constraints; do not ask again which of those already selected hosts was intended. These constraints do not assert world facts. '


def retain_role(state,region,predicate,token,selected,reading=None):
    """A resolved source-role question constrains every later producer here."""
    from .composition_session import current
    runtime=current(state)
    row={'kind':'ESTABLISHED_PREDICATE_ROLE','region_ref':region.region_id,
         'task_scope':runtime.input_signature() if runtime else None,
         'predicate_ref':predicate.token_id,'token_ref':token.token_id,
         'role':selected[0]['candidate_id'],'proof':selected[1],'reading':reading}
    if row not in state.syntax_trace:state.syntax_trace.append(row)


def compatible_bundle(state,region,bundle):
    from .composition_session import current
    runtime=current(state);scope=runtime.input_signature() if runtime else None
    frames={f.predicate_token_ref:f for f in bundle}
    for row in state.syntax_trace:
        if (row.get('kind')!='ESTABLISHED_PREDICATE_ROLE' or row['region_ref']!=region.region_id
                or row['task_scope']!=scope):continue
        from .structural_tasks import licensed
        if not licensed(state,row['proof'],predicate_ref=row['predicate_ref'],token_ref=row['token_ref']):return False
        f=frames.get(row['predicate_ref'])
        if f is None:return False
        chosen=f.semantic.get('proposed_roles',{}).get(row['token_ref'])
        expected=row['role']
        if (chosen is not None if expected=='NO_DIRECT_ROLE' else chosen!=expected):return False
        if row.get('reading'):
            actual=f.semantic.get('morph_bindings',{}).get(row['token_ref'],{})
            # Whole linguistic readings, not analyzer confidence/proof paths.
            fields=('lemma','pos','cases','number','gender','tense','person','mood','features')
            if any(actual.get(k)!=row['reading'].get(k) for k in fields):return False
    from .partial_readings import domains,valid_domain
    from .morphology_domain import clean
    for row in domains(state,region):
        frame=frames.get(row['predicate_ref'])
        actual=frame.semantic.get('morph_bindings',{}).get(row['token_ref']) if frame else None
        if not valid_domain(state,row) or actual is None or clean(actual) not in [v['reading'] for v in row['alternatives']]:return False
    return True


def preserves_nominal_functions(state,tokens,bundle):
    """Selected reference/quantity functions cannot disappear in another producer."""
    from .nominal_functions import rows
    for source in rows(state,tokens):
        if source['function']=='QUANTITY':
            candidates=[g for f in bundle for g in f.semantic.get('qualitative_groups',())]
            if not any(g['head_ref']==source['head_ref'] and
                       g.get('quantity_token_refs')==source['function_refs'] for g in candidates):return False
        elif source['function']=='REFERENCE':
            candidates=[u.get('reference_constraint',{}) for f in bundle
                        for u in f.semantic.get('lexical_units',{}).values()]
            if not any(g.get('head_ref')==source['head_ref'] and
                       g.get('function_refs')==source['function_refs'] and
                       g.get('identity_constraint')==source['identity_constraint'] for g in candidates):return False
    return True


def host_live(state,row):
    from .partial_readings import retired_refs
    from .selection_domains import fingerprint
    from .selection_evidence import selected_candidate
    from .function_inventory import source_basis
    key=row.get('decision_ref');stamp=fingerprint(state,key)
    usable=(key not in retired_refs(state.syntax_trace) and stamp is not None
        and row.get('fingerprint')==stamp and row.get('source_basis')==source_basis(state)
        and row.get('selected') is not None and selected_candidate(state.decisions.get(key))==row['selected'])
    if usable:
        from .dispatch_evidence import observe
        observe(state,'NOMINAL_HOST',row)
    return usable


def frame_hosts_live(state,frame):
    return all(host_live(state,r) for r in frame.semantic.get('nominal_host_evidence',()))
