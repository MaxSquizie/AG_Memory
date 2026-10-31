"""Carry established local attachments into the remaining composition question."""


def question(state,region):
    observe_constraints(state,region)
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


def inspect_bundle(state,region,tokens,bundle,*,nominal=True,require_nominal_projection=False):
    from .composition_session import current
    from .function_inventory import execution_condition
    from .bundle_constraints import inspect,signature
    from dataclasses import asdict
    runtime=current(state);scope=runtime.input_signature() if runtime else None
    condition=execution_condition(state)
    refs=[t.token_id for t in tokens]
    result=inspect(state,region.region_id,scope,refs,bundle,condition,nominal=nominal,require_nominal_projection=require_nominal_projection)
    from .dispatch_evidence import observe
    observe(state,'BUNDLE_CONSTRAINTS',{'region_ref':region.region_id,'task_scope':scope,
        'token_refs':refs,'frames':[asdict(f) for f in bundle],'condition':condition,
        'nominal':nominal,'require_nominal_projection':require_nominal_projection,'signature':signature(result)})
    return result


def compatible_bundle(state,region,bundle):
    return inspect_bundle(state,region,[],bundle,nominal=False)['status']=='REQUIREMENTS_SATISFIED'


def preserves_nominal_functions(state,tokens,bundle):
    from .composition_session import current
    runtime=current(state)
    if runtime and runtime.area_inputs:
        return inspect_bundle(state,runtime.area_inputs[0],tokens,bundle)['status']=='REQUIREMENTS_SATISFIED'
    # Historical callers must supply an explicit area and scope to inspect.
    return False


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
    from .relative_pronoun import binding_live
    from .refinement_host_proof import frame_live as owner_live
    return (binding_live(state,frame) and owner_live(state,frame)
            and all(host_live(state,r) for r in frame.semantic.get('nominal_host_evidence',())))


def constraint_signature(state,region_ref,scope,condition=None):
    """Membership and liveness of obligations, including the initially empty set.

    The query is addressed to one area/input hypothesis. No constraint crosses
    into an unrelated child or occurrence merely because its wording matches.
    """
    from .canonical_ledger import digest
    from .composition_dispatcher import canonical
    from .structural_tasks import _licensed
    from .partial_readings import valid_domain
    records=[]
    for row in state.syntax_trace:
        kind=row.get('kind')
        if (kind not in {'ESTABLISHED_PREDICATE_ROLE','PARTIAL_READING_DOMAIN','NOMINAL_HOST_QUESTION'}
                or row.get('region_ref')!=region_ref or row.get('task_scope')!=scope):continue
        if kind=='ESTABLISHED_PREDICATE_ROLE':
            live=_licensed(state,row['proof'],_branch=condition,predicate_ref=row['predicate_ref'],token_ref=row['token_ref'])
        elif kind=='PARTIAL_READING_DOMAIN':live=valid_domain(state,row)
        else:live=host_live(state,row)
        records.append([row,live])
    return digest(canonical(records))


def observe_constraints(state,region):
    from .composition_session import current
    runtime=current(state)
    if runtime is None:return
    scope=runtime.input_signature()
    from .function_inventory import execution_condition
    condition=execution_condition(state)
    runtime.dispatcher.observe('CONSTRAINT_SET',{'region_ref':region.region_id,'task_scope':scope,
        'condition':condition,'signature':constraint_signature(state,region.region_id,scope,condition)})


def accepts_bundle(state,region,tokens,bundle):
    """Common source obligations for component and grammar alternatives."""
    return inspect_bundle(state,region,tokens,bundle)['status']=='REQUIREMENTS_SATISFIED'
