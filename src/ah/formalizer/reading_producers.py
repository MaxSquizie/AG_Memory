"""P02 typed payload adapters; bindings are built before a selector sees options."""
from dataclasses import asdict
from copy import deepcopy
from . import reading_witnesses as rw
from .canonical_ledger import digest
from .morphology_domain import clean,proposed
from .composition_dispatcher import canonical


def binding(state,release,region,token_ref,reading,use):
    from .composition_session import current
    from .function_inventory import execution_condition
    runtime=current(state)
    scope=runtime.input_signature() if runtime else None
    token=next(t for t in state.evidence if t.token_id==token_ref)
    a=rw.address(state,source_revision=state.observation.get('revision',1),
        region_ref=region.region_id,occurrence_refs=region.token_refs,
        input_scope=scope or digest(['NO_PARENT',region.region_id]),
        resource_version=release.sha256,condition=execution_condition(state))
    return {'token_ref':token_ref,'source_range':[token.start,token.end],
            'reading':canonical(clean(reading)),'use':canonical(use),'address':canonical(a)}


def attach(option,bindings):
    """Return a fresh payload; no post-selection augmentation is permitted."""
    return {**option,'reading_uses':deepcopy(bindings)}


def frame_bindings(state,release,region,frames,*,family,contract=None):
    from .morphology_domain import frame_readings
    result=[]
    for f in frames:
        for location,tid,reading in frame_readings(f):
            if not proposed(reading):continue
            use={'kind':family,'frame_ref':f.frame_id,'location':location,
                 'predicate_ref':f.predicate_token_ref,'role':f.semantic.get('proposed_roles',{}).get(tid),
                 'parent_contract':contract}
            result.append(binding(state,release,region,tid,reading,use))
    return result


def restore(raw):
    a=raw['address'];a={**a,'occurrence_refs':tuple(a['occurrence_refs'])}
    return rw.Witness(**{**raw,'address':rw.Address(**a),
        'source_range':tuple(raw['source_range']),'parent_refs':tuple(raw['parent_refs'])})


def from_selection(state,decision_ref,candidate_id,entry,*,domain=None):
    a={**entry['address'],'occurrence_refs':tuple(entry['address']['occurrence_refs'])};a=rw.Address(**a)
    from .reading_decisions import inspect
    inspected=inspect(state,decision_ref,a.condition)
    proof=inspected['proof']
    if domain is not None and inspected['selected'] is None:
        payload=next(v for v in domain['alternatives'] if v['candidate_id']==candidate_id)
        kind='SELECTED_DOMAIN';basis=rw.selection_basis(state,domain)
    elif proof is not None:
        payload=next(v for r in reversed(state.syntax_trace) if r.get('kind')=='STRUCTURAL_TASK'
            and r.get('decision_ref')==decision_ref for v in r.get('alternatives',()) if v['candidate_id']==candidate_id)
        kind='DERIVED';basis=rw.selection_basis(state,proof)
    else:
        record=state.component_probe_records.get(decision_ref,{})
        packet=record.get('payload_contract')
        if packet is None:raise ValueError('READING_SELECTION_PAYLOAD_MISSING')
        payload=next(v for v in packet['options'] if v['candidate_id']==candidate_id)
        proof={'decision_ref':decision_ref,'candidate_id':candidate_id,'payload_hash':digest(payload)}
        kind='DERIVED';basis=rw.direct_basis(state,decision_ref)
    return rw.witness(a,kind,entry['token_ref'],entry['source_range'],entry['reading'],entry['use'],
        rule='SELECTED_READING_USE_V1',payload=payload,proof=proof,domain=domain,basis=basis)


def issue(state,decision_ref,candidate_id,entries,*,domain=None):
    from .morphology_domain import license_use
    for entry in entries:
        if not proposed(entry['reading']):continue
        w=from_selection(state,decision_ref,candidate_id,entry,domain=domain)
        license_use(state,entry['token_ref'],entry['reading'],decision_ref,candidate_id,witness=w)


def assessment(state,w):
    """Production wrapper observes both successful and failed strict reads."""
    from .dispatch_evidence import observe
    from .function_inventory import execution_condition
    condition=execution_condition(state)
    scope=use_scope(state)
    transfer=transfer_receipt(state,w,scope)
    result=evaluate(state,w,condition,scope,transfer)
    if result.selected_use and transfer is not None:
        from .composition_session import current
        runtime=current(state)
        if runtime is not None:
            imported=transfer['import']
            runtime.dispatcher.read(imported['parent_task'],imported['parent_revision'])
    receipt={'witness':asdict(w),'condition':condition,'scope':scope,'transfer':transfer,'assessment':canonical(result)}
    observe(state,'READING_USE',receipt)
    return result


def function_entries(state,release,region,*,kind,head_ref,function_refs,case=None):
    """Typed source-function projections; no dictionary lemma/paradigm is inferred."""
    from .state import MorphVariant
    from .morphology_domain import offer
    by_id={t.token_id:t for t in state.evidence};refs=list(function_refs);marker=by_id[refs[0]]
    result=[]
    if kind=='RELATION':
        proposals=offer(state,marker,[MorphVariant(' '.join(by_id[r].span for r in refs),'PREP',origin='CONTEXTUAL')],'RELATION_FUNCTION',refs)
    elif kind=='QUANTITY_CASE':
        proposals=offer(state,marker,[MorphVariant(marker.span,'NUMR',frozenset({case}),origin='CONTEXTUAL')],'QUANTITY_FUNCTION',refs)
    else:proposals=()
    for v in proposals:result.append(binding(state,release,region,marker.token_id,v,
        {'kind':kind,'head_ref':head_ref,'function_refs':refs,'external_case':case}))
    if kind=='SHARED_NOMINAL':
        token=by_id[head_ref]
        for v in offer(state,token,[MorphVariant(token.span.casefold(),'NOUN',origin='CONTEXTUAL')],'SHARED_NOMINAL_FUNCTION',refs):
            result.append(binding(state,release,region,head_ref,v,{'kind':kind,'head_ref':head_ref,'function_refs':refs}))
    return result


def proof_entries(state,proof):
    for row in reversed(state.syntax_trace):
        if row.get('kind')=='STRUCTURAL_TASK' and row.get('decision_ref')==proof['decision_ref']:
            for value in row.get('alternatives',()):
                if value.get('candidate_id')==proof['candidate_id'] and digest(value)==proof.get('payload_hash'):
                    return deepcopy(value.get('reading_uses',[]))
    raise ValueError('READING_PROJECTION_PAYLOAD_MISSING')


def evaluate(state,w,condition,scope=None,transfer=None,provider_results=None):
    if w.address.condition is not None:
        from .structural_conditions import allows
        if condition is None or not allows(state,w.address.condition,condition):
            return rw.Assessment('CONFLICT','CONDITIONAL_USE_OUTSIDE_SCOPE')
    if scope is not None and (scope['input_scope']!=w.address.input_scope or scope['region_ref']!=w.address.region_ref):
        if not oov_transfer(state,w,scope,transfer,provider_results):
            return rw.Assessment('CONFLICT','READING_USE_OUTSIDE_SCOPE')
    return rw.historical(state,w,expected_address=w.address)


def query_rows(state,token_ref,scope,reading=None):
    """One addressed eligibility selector for lookup and its absence receipt."""
    rows=[]
    imports=[r for r in state.syntax_trace if r.get('kind')=='MORPHOLOGY_FUNCTION_IMPORT'
        and r.get('token_ref')==token_ref and (scope is None or r.get('task_scope')==scope['morphology_scope'])]
    imported_refs={r['function_ref'] for r in imports}
    for r in state.syntax_trace:
        if r.get('token_ref')!=token_ref:continue
        kind=r.get('kind')
        if reading is not None and kind in {'MORPHOLOGY_USE','MORPHOLOGY_PROPOSAL'} and r.get('reading')!=clean(reading):continue
        if kind=='MORPHOLOGY_USE':
            if scope is not None and r.get('witness',{}).get('address',{}).get('input_scope')!=scope['input_scope']:
                if not r.get('witness') or transfer_receipt(state,restore(r['witness']),scope) is None:continue
        elif kind in {'MORPHOLOGY_PROPOSAL','MORPHOLOGY_FUNCTION_RESTRICTION','MORPHOLOGY_FUNCTION_IMPORT'}:
            if scope is not None and r.get('task_scope') not in (None,scope['morphology_scope']):
                if kind!='MORPHOLOGY_FUNCTION_RESTRICTION' or digest(r) not in imported_refs:continue
        else:continue
        rows.append(r)
    return list({digest(r):r for r in rows}.values())


def query_snapshot(state,token_ref,scope,reading=None):
    return digest(query_rows(state,token_ref,scope,reading))


def query_refs(state,token_ref,scope,reading=None):
    return {r['decision_ref'] for r in query_rows(state,token_ref,scope,reading) if r.get('decision_ref')}


def observe_query(state,token_ref,reading):
    from .dispatch_evidence import observe
    scope=use_scope(state)
    observe(state,'READING_QUERY',{'token_ref':token_ref,'scope':scope,'reading':clean(reading),
        'signature':query_snapshot(state,token_ref,scope,reading)})


def use_scope(state):
    from .composition_session import current
    runtime=current(state)
    if runtime is None or not getattr(runtime,'area_inputs',None):return None
    region,tokens,_=runtime.area_inputs
    return {'input_scope':runtime.input_signature(),'region_ref':region.region_id,
            'token_refs':[t.token_id for t in tokens],'morphology_scope':runtime.morphology_scope}


def transfer_receipt(state,w,scope):
    """Freeze an existing, explicitly addressed parent import; never create one."""
    import json
    if scope is None or (scope['input_scope']==w.address.input_scope and scope['region_ref']==w.address.region_ref):return None
    if json.loads(w.use_json).get('kind')!='OOV_POS':return None
    proof=json.loads(w.proof_json) or json.loads(w.domain_json) or {}
    for row in state.syntax_trace:
        if (row.get('kind')!='MORPHOLOGY_FUNCTION_RESTRICTION' or row.get('token_ref')!=w.token_ref
            or row.get('decision_ref')!=proof.get('decision_ref')):continue
        for imported in state.syntax_trace:
            if (imported.get('kind')=='MORPHOLOGY_FUNCTION_IMPORT' and imported.get('function_ref')==digest(row)
                and imported.get('task_scope')==scope['morphology_scope'] and imported.get('token_ref')==w.token_ref):
                return deepcopy({'import':imported,'restriction':row})
    return None


def provider_live(state,imported,provider_results=None):
    key=(imported['parent_task'],imported['parent_revision'])
    if provider_results is not None:return provider_results.get(key,False)
    from .dispatch_history import valid
    return valid(state,*key)


def oov_transfer(state,w,scope,transfer,provider_results=None):
    """Pure historical check; task subscription belongs to assessment()."""
    import json
    if transfer is None or transfer!=transfer_receipt(state,w,scope):return False
    if w.token_ref not in scope['token_refs']:return False
    imported=transfer['import'];row=transfer['restriction'];address=row.get('address',{})
    if not provider_live(state,imported,provider_results):return False
    if (address.get('token_ref')!=w.token_ref or address.get('source_range')!=list(w.source_range)
        or address.get('source_uid')!=state.source_uid
        or row.get('interpretation_version')!=state.interpretation_version
        or address.get('task_scope')!=row.get('task_scope')):return False
    domain=row['function_domain']
    if row['decision_ref']!=domain['decision_ref']:return False
    values=domain['alternatives']
    if len(values)!=1 or values[0].get('address')!=address:return False
    if values[0]['candidate_id']!=json.loads(w.reading_json)['pos']:return False
    from .validation_graph import validate
    return validate('DOMAIN',state,domain)


def memberships(state,domain):
    """Retaining alternatives proves membership, never a scalar selected use."""
    record=domain.record();result=[]
    for payload in domain.values:
        for entry in payload.get('reading_uses',()):
            a=rw.Address(**{**entry['address'],'occurrence_refs':tuple(entry['address']['occurrence_refs'])})
            w=rw.witness(a,'SELECTED_DOMAIN',entry['token_ref'],entry['source_range'],entry['reading'],entry['use'],
                rule='SELECTED_READING_USE_V1',payload=payload,domain=record,basis=rw.selection_basis(state,record))
            checked=assessment(state,w)
            if checked.permission!='DOMAIN_MEMBERSHIP':raise ValueError('READING_DOMAIN_MEMBERSHIP_UNGROUNDED')
            result.append(asdict(w))
    return result
