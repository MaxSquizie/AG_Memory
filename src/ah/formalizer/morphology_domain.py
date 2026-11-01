"""Occurrence readings shared by producers and selected with typed relations.

The source evidence is immutable. Proposals are serialized, addressed records;
only a selected relation licenses their use. A singleton is not such a license.
"""
from .reading_decisions import selected as selected_reading_decision
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


def function_restrictions(state,token_ref):
    """Direct restrictions plus explicitly imported occurrence evidence."""
    scope=scope_fields(state).get('task_scope')
    imports={r['function_ref'] for r in state.syntax_trace
             if r.get('kind')=='MORPHOLOGY_FUNCTION_IMPORT' and r.get('task_scope')==scope
             and r.get('token_ref')==token_ref}
    return [r for r in state.syntax_trace if r.get('kind')=='MORPHOLOGY_FUNCTION_RESTRICTION'
            and r.get('token_ref')==token_ref and (in_scope(state,r) or digest(r) in imports)]


def function_use(state,token_ref,reading,decision_ref,candidate_id):
    """Strict existing-use lookup; a selected decision alone grants no use."""
    from .reading_producers import restore,assessment,observe_query,query_rows,use_scope
    for row in query_rows(state,token_ref,use_scope(state)):
        if (row.get('kind')=='MORPHOLOGY_USE' and row.get('token_ref')==token_ref
            and row.get('reading')==clean(reading) and row.get('decision_ref')==decision_ref
            and row.get('candidate_id')==candidate_id and row.get('witness')):
            if assessment(state,restore(row['witness'])).selected_use:return True
    observe_query(state,token_ref,reading)
    return False


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
        functions=function_restrictions(state,token.token_id)
        if functions:
            supported=function_support(state,token,functions[-1])
            if not supported:raise ValueError('MORPHOLOGY_FUNCTION_UNGROUNDED')
            readings={k:v for k,v in readings.items() if v.pos in supported}
        restrictions=[row for row in state.syntax_trace if row.get('kind')=='MORPHOLOGY_DOMAIN_RESTRICTION' and in_scope(state,row) and row['token_ref']==token.token_id]
        if restrictions:
            row=restrictions[-1];decision=state.decisions.get(row['decision_ref'])
            if selected_reading_decision(state,row['decision_ref']) is not None and row['candidate_id'] in decision.selected:
                readings={k:v for k,v in readings.items() if clean(v)==row['reading']}
        result.append(replace(token,variants=tuple(readings.values())))
    return result


def license_use(state,token_ref,reading,decision_ref,candidate_id,*,witness=None):
    if not proposed(reading):return
    from dataclasses import asdict
    from .reading_producers import assessment
    if witness is None:raise ValueError('MORPHOLOGY_USE_WITNESS_REQUIRED')
    import json
    proof=json.loads(witness.proof_json) or json.loads(witness.domain_json) or {}
    if (witness.token_ref!=token_ref or json.loads(witness.reading_json)!=clean(reading)
        or proof.get('decision_ref')!=decision_ref or proof.get('candidate_id',candidate_id)!=candidate_id
        or not assessment(state,witness).selected_use):raise ValueError('MORPHOLOGY_USE_UNGROUNDED')
    row={'kind':'MORPHOLOGY_USE','token_ref':token_ref,'reading':clean(reading),
         'decision_ref':decision_ref,'candidate_id':candidate_id,'witness':asdict(witness)}
    if row not in state.syntax_trace:state.syntax_trace.append(row)


def attested(state,token,reading):
    if not proposed(reading):return False
    from .reading_producers import observe_query,query_rows,use_scope
    eligible=query_rows(state,token.token_id,use_scope(state))
    refs=reading.get('evidence_refs',())
    if refs[0].startswith('nominal-use:'):
        from .contextual_substantives import nominal_use
        generated=any(digest(clean(nominal_use(token,v)))==digest(clean(reading)) for v in token.variants
                      if v.pos=='ADJF' and not v.features & {'Anum','Apro'})
    else:
        generated=any(row.get('kind')=='MORPHOLOGY_PROPOSAL' and row['token_ref']==token.token_id
                      and row['proposal_ref']==refs[0] and row['reading']==clean(reading)
                      for row in eligible)
    if not generated:
        observe_query(state,token.token_id,reading)
        return False
    for row in eligible:
        if row.get('kind')!='MORPHOLOGY_USE' or row['token_ref']!=token.token_id or row['reading']!=clean(reading):continue
        if function_use(state,token.token_id,reading,row['decision_ref'],row['candidate_id']):return True
    observe_query(state,token.token_id,reading)
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
            if reading.get('origin') in {'CONTEXTUAL','RECOVERED'} and not reading_attested(state,tid,reading):
                raise ValueError('MORPHOLOGY_USE_UNGROUNDED')


def strict_use(state,witness,*,expected_address,original=None,parents=(),historical=False):
    """Explicit uncached P01 API. Failure never falls back to function_use.

    Production reading-use adapters observe through reading_producers.assessment.
    Direct callers must provide their own explicit dependency observations.
    """
    from .reading_witnesses import historical as inspect_historical,validate
    evaluator=inspect_historical if historical else validate
    return evaluator(state,witness,expected_address=expected_address,original=original,parents=parents)
