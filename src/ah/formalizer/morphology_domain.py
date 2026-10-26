"""Occurrence readings shared by producers and selected with typed relations.

The source evidence is immutable. Proposals are serialized, addressed records;
only a selected relation licenses their use. A singleton is not such a license.
"""
from .selection_evidence import selected_candidate
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph


def clean(reading):
    raw=_morph(reading) if not isinstance(reading,dict) else reading
    return {k:list(v) if isinstance(v,tuple) else v for k,v in raw.items() if k!='score'}


def proposed(reading):
    refs=reading.get('evidence_refs',())
    return bool(reading.get('origin')=='CONTEXTUAL' and refs and
                refs[0].startswith(('nominal-use:','usage-reading:')))


def scope_fields(state):
    from .composition_session import current
    runtime=current(state)
    scope=runtime.morphology_scope if runtime else None
    return {'task_scope':scope} if scope else {}


def in_scope(state,row):
    scope=scope_fields(state).get('task_scope')
    return not row.get('task_scope') or row.get('task_scope')==scope


def function_support(state,token,row):
    """A POS domain licenses exactly one occurrence in its recorded hypothesis."""
    from .partial_readings import valid_domain
    address=row.get('address',{})
    domain=row.get('function_domain',{})
    if (address.get('token_ref')!=token.token_id or address.get('source_range')!=[token.start,token.end]
            or address.get('source_uid')!=state.source_uid
            or row.get('interpretation_version')!=state.interpretation_version
            or address.get('task_scope')!=row.get('task_scope')
            or row.get('decision_ref')!=domain.get('decision_ref') or not valid_domain(state,domain)):
        return frozenset()
    values=domain['alternatives']
    if any(v.get('address')!=address for v in values):return frozenset()
    return frozenset(v['candidate_id'] for v in values)


def function_use(state,token_ref,reading,decision_ref,candidate_id):
    decision=state.decisions.get(decision_ref)
    if decision is None or decision.slot_id!='structural_oov_function':return True
    token=next((t for t in state.evidence if t.token_id==token_ref),None)
    return bool(token and reading.get('pos')==candidate_id and
        not reading.get('cases') and all(reading.get(k) is None for k in ('number','gender','person','tense','mood'))
        and not reading.get('features') and any(candidate_id in function_support(state,token,row)
            for row in state.syntax_trace if row.get('kind')=='MORPHOLOGY_FUNCTION_RESTRICTION'
            and row.get('token_ref')==token_ref and row.get('decision_ref')==decision_ref))


def offer(state,token,readings,source,anchors=()):
    result=[]
    for v in readings:
        key='usage-reading:'+digest([token.token_id,source,clean(v),list(anchors),scope_fields(state)])
        value=replace(v,origin='CONTEXTUAL',evidence_refs=(key,token.token_id,*anchors))
        row={'kind':'MORPHOLOGY_PROPOSAL',**scope_fields(state),'proposal_ref':key,'token_ref':token.token_id,
             'source':source,'reading':clean(value),'source_reading':clean(v),'anchor_refs':list(anchors)}
        if row not in state.syntax_trace:state.syntax_trace.append(row)
        result.append(value)
    return tuple(result)


def project(state,tokens):
    from .nominal_readings import variant
    by_token={};owned={t.token_id for t in tokens}
    for row in state.syntax_trace:
        if row.get('kind')=='MORPHOLOGY_PROPOSAL' and in_scope(state,row) and set(row.get('anchor_refs',()))<=owned:
            by_token.setdefault(row['token_ref'],{})[digest(row['reading'])]=variant(row['reading'])
    result=[]
    for token in tokens:
        readings={digest(clean(v)):v for v in token.variants}
        readings.update(by_token.get(token.token_id,{}))
        functions=[row for row in state.syntax_trace if row.get('kind')=='MORPHOLOGY_FUNCTION_RESTRICTION'
                   and in_scope(state,row) and row['token_ref']==token.token_id]
        if functions:
            supported=function_support(state,token,functions[-1])
            if not supported:raise ValueError('MORPHOLOGY_FUNCTION_UNGROUNDED')
            readings={k:v for k,v in readings.items() if v.pos in supported}
        restrictions=[row for row in state.syntax_trace if row.get('kind')=='MORPHOLOGY_DOMAIN_RESTRICTION' and in_scope(state,row) and row['token_ref']==token.token_id]
        if restrictions:
            row=restrictions[-1];decision=state.decisions.get(row['decision_ref'])
            if selected_candidate(decision) is not None and row['candidate_id'] in decision.selected:
                readings={k:v for k,v in readings.items() if clean(v)==row['reading']}
        result.append(replace(token,variants=tuple(readings.values())))
    return result


def license_use(state,token_ref,reading,decision_ref,candidate_id):
    if not proposed(reading):return
    decision=state.decisions.get(decision_ref)
    if (selected_candidate(decision) is None or candidate_id not in decision.selected
            or not function_use(state,token_ref,reading,decision_ref,candidate_id)):
        raise ValueError('MORPHOLOGY_USE_UNGROUNDED')
    row={'kind':'MORPHOLOGY_USE','token_ref':token_ref,'reading':clean(reading),
         'decision_ref':decision_ref,'candidate_id':candidate_id}
    if row not in state.syntax_trace:state.syntax_trace.append(row)


def attested(state,token,reading):
    if not proposed(reading):return False
    refs=reading.get('evidence_refs',())
    if refs[0].startswith('nominal-use:'):
        from .contextual_substantives import nominal_use
        generated=any(digest(clean(nominal_use(token,v)))==digest(clean(reading)) for v in token.variants
                      if v.pos=='ADJF' and not v.features & {'Anum','Apro'})
    else:
        generated=any(row.get('kind')=='MORPHOLOGY_PROPOSAL' and row['token_ref']==token.token_id
                      and row['proposal_ref']==refs[0] and row['reading']==clean(reading)
                      for row in state.syntax_trace)
    if not generated:return False
    for row in state.syntax_trace:
        if row.get('kind')!='MORPHOLOGY_USE' or row['token_ref']!=token.token_id or row['reading']!=clean(reading):continue
        decision=state.decisions.get(row['decision_ref'])
        if (selected_candidate(decision) is not None and row['candidate_id'] in decision.selected
                and function_use(state,token.token_id,reading,row['decision_ref'],row['candidate_id'])):return True
    return False


def frame_readings(frame):
    """Typed occurrences: a quantity's head is distinct from its outer case."""
    sem=frame.semantic
    for field in ('morph_bindings','pp_readings'):
        for tid,reading in sem.get(field,{}).items():yield 'MORPH',tid,reading
    for row in sem.get('nominal_dependencies',()):yield 'MORPH',row['head_ref'],row['morph']
    for tid,row in sem.get('group_readings',{}).items():
        yield 'HEAD',tid,row['selected_head_reading']
        yield 'MORPH',tid,row['external_reading']


def validate_uses(state,frames):
    from .nominal_readings import attested as reading_attested
    for frame in frames:
        for _,tid,reading in frame_readings(frame):
            if proposed(reading) and not reading_attested(state,tid,reading):
                raise ValueError('MORPHOLOGY_USE_UNGROUNDED')
