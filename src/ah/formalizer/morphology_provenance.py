"""Versioned producer records and source morphology, separate from live overlays.

Readers only validate issued records. They never turn a current trace row or a
published recovery into source evidence by taking a new snapshot.
"""
import json
from dataclasses import asdict,is_dataclass
from .canonical_ledger import digest
from .composition_dispatcher import canonical


def normalized(value):
    if is_dataclass(value):value=asdict(value)
    if isinstance(value,dict):
        reading={'lemma','pos','cases','origin','evidence_refs'}<=set(value)
        token={'token_id','span','variants','start','end'}<=set(value)
        return {k:normalized(v) for k,v in value.items() if not ((reading or token) and k=='score')}
    if isinstance(value,(tuple,list)):return [normalized(v) for v in value]
    if isinstance(value,(set,frozenset)):return sorted(normalized(v) for v in value)
    return value


def frozen(value):
    return json.dumps(normalized(value),ensure_ascii=False,sort_keys=True,separators=(',',':'))


def token_source(token):
    return {'token_ref':token.token_id,'surface':token.span,'range':[token.start,token.end],
            'readings':sorted((normalized(v) for v in token.variants),key=frozen),
            'indices':normalized({'lemma':token.lemma,'pos':token.pos,'cases':token.cases,'lex_status':token.lex_status})}


def capture(state,manifest=None,release=None):
    """Source-adapter operation, called once after T1 and before transformations."""
    if release is not None and not state.resource_snapshot:
        state.resource_snapshot={"snapshot_id":release.sha256}
    if state.morphology_source:return
    state.morphology_manifest=manifest or {'provider':'DECLARED_SOURCE_ADAPTER','resource':state.resource_snapshot.copy()}
    rows=[token_source(t) for t in state.evidence]
    if any(v.get('origin') in {'CONTEXTUAL','RECOVERED','PREDICTED'} for r in rows for v in r['readings']):
        raise ValueError('MORPHOLOGY_SOURCE_ALREADY_DERIVED')
    state.morphology_source=frozen({'source_uid':state.source_uid,'text':state.text,
        'revision':state.observation.get('revision',1),'manifest':state.morphology_manifest,'tokens':rows})


def resource(state):
    from .composition_session import current
    runtime=current(state)
    return runtime.release.sha256 if runtime is not None else state.resource_snapshot.get('snapshot_id')


def issue(state,row,refs,*,release=None):
    """Seal a complete producer row and its addressed source inputs."""
    if not state.morphology_source:raise ValueError('MORPHOLOGY_SOURCE_MISSING')
    from .function_inventory import execution_condition
    row.setdefault('condition',execution_condition(state))
    refs=tuple(dict.fromkeys(refs));source=json.loads(state.morphology_source)
    tokens={r['token_ref']:r for r in source['tokens']}
    if any(ref not in tokens for ref in refs):raise ValueError('MORPHOLOGY_SOURCE_OCCURRENCE_MISSING')
    record={'row':normalized({k:v for k,v in row.items() if k!='morphology_ref'}),'sources':[tokens[ref] for ref in refs],
            'source_basis':digest(state.morphology_source),'interpretation_version':state.interpretation_version,
            'resource':release.sha256 if release is not None else resource(state)}
    data=frozen(record);ref='morphology-record:'+digest(data)
    state.morphology_records.setdefault(ref,data);row['morphology_ref']=ref
    return row


def source_live(state,source):
    token=next((t for t in state.evidence if t.token_id==source['token_ref']),None)
    if token is None:return False
    current=token_source(token)
    if current==source:return True
    # A publication is an explicit projection, never a replacement of ORIGINAL.
    for row in state.syntax_trace:
        if row.get('kind')!='MORPHOLOGY_PUBLICATION' or row.get('token_ref')!=token.token_id:continue
        record=recorded(state,row)
        if (record and record['sources']==[source] and normalized(row['published'])==current
            and publication_live(state,row,source)):return True
    return False


def recorded(state,row):
    data=state.morphology_records.get(row.get('morphology_ref'))
    if data is None or 'morphology-record:'+digest(data)!=row.get('morphology_ref'):return None
    record=json.loads(data)
    if (record['row']!=normalized({k:v for k,v in row.items() if k!='morphology_ref'}) or record['source_basis']!=digest(state.morphology_source)
        or record['interpretation_version']!=state.interpretation_version):return None
    source=json.loads(state.morphology_source)
    if source.get('manifest')!=state.morphology_manifest:return None
    if (source['source_uid']!=state.source_uid or source['text']!=state.text
        or source['revision']!=state.observation.get('revision',1)):return None
    current=resource(state)
    if record['resource']!=current:return None
    return record


def _record_live(state,row,provider_results=None):
    if not any(r.get('morphology_ref')==row.get('morphology_ref') and normalized(r)==normalized(row) for r in state.syntax_trace):return False
    record=recorded(state,row)
    from .structural_conditions import historical
    if row.get('condition') is not None and not historical(state,row['condition']):return False
    return bool(record and all(source_live(state,s) for s in record['sources']) and parents_live(state,row,provider_results))


def _original(state,token_ref,reading):
    if not state.morphology_source:return False
    source=json.loads(state.morphology_source)
    if source.get('manifest')!=state.morphology_manifest:return False
    if (source['source_uid']!=state.source_uid or source['text']!=state.text
        or source['revision']!=state.observation.get('revision',1)):return False
    row=next((r for r in source['tokens'] if r['token_ref']==token_ref),None)
    bound=source['manifest'].get('resource',{}).get('snapshot_id')
    if bound is not None and bound!=resource(state):return False
    return bool(row and source_live(state,row) and normalized(reading) in row['readings']
                and reading.get('origin') in {'DICTIONARY','DECLARED','NONLEXICAL'})


def recovery_live(state,row):
    """Check the frozen choice and exact inflection output before any use."""
    from .reading_decisions import receipt_live,inspect
    from .nominal_readings import variant
    from .morphology_domain import clean
    from dataclasses import replace
    if not recorded(state,row):return False
    proof=row.get('selection_receipt')
    if not proof or not receipt_live(state,proof):return False
    if inspect(state,proof['decision_ref'],proof.get('condition'))['selected']!=row.get('selected'):return False
    option=next((o for o in row['options'] if o['candidate_id']==row['selected']),None)
    if not option or option.get('head_ref')!=row['head_ref']:return False
    expected=replace(variant(option['replacement_reading']),origin='RECOVERED',
        evidence_refs=(*option['replacement_reading'].get('evidence_refs',()),row['head_ref'],proof['decision_ref']))
    return (clean(expected)==clean(row['recovered_reading'])
        and row['lexical_recovery']['surface']==option['replacement_surface']
        and row['lexical_recovery']['decision_ref']==proof['decision_ref'])


def publication_live(state,row,source):
    """Recovery depends on ORIGINAL, never on its own publication."""
    parent=next((r for r in state.syntax_trace if r.get('morphology_ref')==row.get('recovery_ref')),None)
    record=recorded(state,parent) if parent else None
    if not record or parent.get('kind')!='AGREEMENT_RECOVERY' or not recovery_live(state,parent):return False
    if parent['token_ref']!=source['token_ref'] or sorted(normalized(parent['original_variants']),key=frozen)!=source['readings']:return False
    if any(v.get('origin')!='DICTIONARY' for v in parent['original_variants']):return False
    published=row['published'];reading=normalized(parent['recovered_reading'])
    expected={**source,'readings':[reading], 'indices':{'lemma':reading['lemma'],'pos':reading['pos'],
        'cases':reading['cases'],'lex_status':'RECOVERY_SELECTED'}}
    if normalized(published)!=expected:return False
    return all(s==source or source_live(state,s) for s in record['sources'])


def parents_live(state,row,provider_results=None):
    from .nominal_readings import available
    kind=row.get('kind')
    if kind=='AGREEMENT_RECOVERY':return recovery_live(state,row)
    if kind=='MORPHOLOGY_PUBLICATION':
        record=recorded(state,row)
        return bool(record and len(record['sources'])==1 and publication_live(state,row,record['sources'][0]))
    if kind=='MORPHOLOGY_FUNCTION_IMPORT':
        from .reading_producers import provider_live
        parent=next((r for r in state.syntax_trace if r.get('kind')=='MORPHOLOGY_FUNCTION_RESTRICTION'
                     and digest(r)==row.get('function_ref')),None)
        return bool(parent and live(state,parent) and provider_live(state,row,provider_results))
    if kind=='MORPHOLOGY_FUNCTION_RESTRICTION':
        from .partial_readings import valid_domain
        return valid_domain(state,row['function_domain'])
    if kind=='MORPHOLOGY_DOMAIN_RESTRICTION':
        from .reading_decisions import receipt_live
        return bool(row.get('selection_receipt') and receipt_live(state,row['selection_receipt']))
    if kind in {'QUANTITY_COMPOSITION','NOMINAL_REFERENCE_GROUP','NOMINAL_FUNCTION'}:
        from .reading_decisions import receipt_live
        from .structural_tasks import _licensed
        if row.get('selection_receipt') and not receipt_live(state,row['selection_receipt']):return False
        proofs=row.get('source_proofs',row.get('proofs',()))
        if not row.get('selection_receipt') and not proofs:return False
        for proof in proofs:
            result=_licensed(state,proof,_branch=row.get('condition'))
            from .dispatch_evidence import observe
            observe(state,'CONDITIONAL_PROOF',{'proof':proof,'expected_payload':{},'condition':row.get('condition')},result)
            if not result:return False
    return all(available(state,tid,r,condition=row.get('condition')) for tid,r in parent_inputs(row))


def parent_inputs(row):
    kind=row.get('kind')
    inputs=[]
    if kind=='MORPHOLOGY_PROPOSAL':
        inputs=[(row['token_ref'],r) for r in row['input_token']['readings']]
    elif kind=='MORPHOLOGY_DOMAIN':
        inputs=[(row['token_ref'],r) for r in row['source_variants']]
    elif kind in {'QUANTITY_COMPOSITION','NOMINAL_REFERENCE_GROUP'}:
        values=row['internal_readings']
        inputs=([(tid,r) for tid,rs in values.items() for r in rs] if isinstance(values,dict)
                else [(row['head_ref'],r) for r in values])
        inputs += [(row['marker_ref'],r) for r in row.get('marker_variants',())]
        inputs += [(row['head_ref'],r) for rs in row.get('internal_by_case',{}).values() for r in rs]
    return inputs


from contextvars import ContextVar
_checking=ContextVar('morphology_provenance_checking',default=None)


class _Dependency(BaseException):
    def __init__(self,state,row,key,providers):self.state,self.row,self.key,self.providers=state,row,key,providers


def _live(state,row,provider_results=None):
    # Trampoline: dependencies suspend the current pure check, never consume
    # another Python call frame. Results live only for this validation request.
    key=(id(state),frozen(row));current=_checking.get()
    if current is not None:
        results,pending=current
        if key in results:return results[key]
        if key in pending:return False
        raise _Dependency(state,row,key,provider_results)
    results={};pending={key};stack=[(state,row,key,provider_results)]
    token=_checking.set((results,pending))
    try:
        while stack:
            owner,value,identity,providers=stack[-1]
            try:result=_record_live(owner,value,providers)
            except _Dependency as dependency:
                pending.add(dependency.key)
                stack.append((dependency.state,dependency.row,dependency.key,dependency.providers));continue
            results[identity]=bool(result);pending.remove(identity);stack.pop()
        return results[key]
    finally:_checking.reset(token)


def live(state,row):
    from .dispatch_evidence import observe
    result=_live(state,row)
    observe(state,'MORPHOLOGY_PROVENANCE',{'row':canonical(row)},result)
    return result


def original(state,token_ref,reading):
    from .dispatch_evidence import observe
    result=_original(state,token_ref,reading)
    observe(state,'MORPHOLOGY_ORIGINAL',{'token_ref':token_ref,'reading':normalized(reading)},result)
    return result


def group_live(state,group,*,condition):
    """A consumer may add selected head/output fields, not rewrite its producer."""
    ref=group.get('morphology_ref')
    row=next((r for r in state.syntax_trace if r.get('morphology_ref')==ref),None)
    if row is None or row.get('kind')!='QUANTITY_COMPOSITION':return False
    return usable_condition(state,row,condition) and all(normalized(group.get(k))==normalized(v) for k,v in row.items()) and live(state,row)


def probe_refs(state,row):
    """Exact transformation ancestry for addressed read retirement."""
    from .morphology_domain import clean
    from .dispatch_evidence import evidence_probe_refs
    refs=set();seen=set();pending=[row]
    while pending:
        value=pending.pop();identity=frozen(value)
        if identity in seen:continue
        seen.add(identity)
        refs.update(evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':None,'condition':value.get('condition')}))
        objects=[value]
        while objects:
            obj=objects.pop()
            if isinstance(obj,dict):
                if obj.get('decision_ref'):refs.add(obj['decision_ref'])
                objects.extend(obj.values())
            elif isinstance(obj,(list,tuple)):objects.extend(obj)
        if value.get('witness'):
            refs.update(evidence_probe_refs(state,'READING_USE',{'witness':value['witness']}))
        for proof in value.get('source_proofs',value.get('proofs',())):
            refs.update(evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':proof,'condition':value.get('condition')}))
        for candidate in state.syntax_trace:
            if (value.get('recovery_ref') and candidate.get('morphology_ref')==value['recovery_ref']
                or value.get('function_ref') and digest(candidate)==value['function_ref']):pending.append(candidate)
        for tid,reading in parent_inputs(value):
            for candidate in state.syntax_trace:
                if candidate.get('token_ref',candidate.get('head_ref'))!=tid:continue
                outputs=[candidate.get('reading',{}),candidate.get('recovered_reading',{}),*candidate.get('proposals',())]
                if any(clean(output)==clean(reading) for output in outputs):pending.append(candidate)
                elif candidate.get('kind') in {'QUANTITY_COMPOSITION','NOMINAL_REFERENCE_GROUP'}:
                    if candidate.get('decision_ref') in reading.get('evidence_refs',()):pending.append(candidate)
    return refs


def usable_condition(state,row,condition):
    required=row.get('condition')
    if required is None:return True
    from .structural_conditions import allows
    return condition is not None and allows(state,required,condition)
