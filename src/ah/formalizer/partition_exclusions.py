"""Exact partition combinations and revocable negative confirmation evidence.

A rejected combination never exhausts its producer or refutes its relation.
Historical evidence and applicability in the current branch are separate checks.
"""
from copy import deepcopy
from .canonical_ledger import digest
from .task_contracts import SelectionPurpose
from .structural_conditions import execution_basis,historical,active


def semantic(option):
    value={k:deepcopy(v) for k,v in option.items() if k not in
           {'candidate_id','label','relation_proof','owner_proof','combination_ref'}}
    value['shared_functions']=[{k:v for k,v in f.items() if k!='proof'}
                               for f in value.get('shared_functions',())]
    if value.get('shared_material') is not None:
        value['shared_material']={'selected_refs':list(value['shared_material']['collection']['selected_refs'])}
    return value


def address(state,region,tokens,cfg,option):
    condition=active(state)
    payload={'source_uid':state.source_uid,'interpretation_version':state.interpretation_version,
        'region_ref':region.region_id,'source_range':list(region.source_range),
        'token_refs':[t.token_id for t in tokens],'basis':execution_basis(state,cfg),
        'condition':condition.record() if condition else None,'proposal':semantic(option)}
    return {'combination_ref':'partition-combination:'+digest(payload),**payload}


def offer(state,region,tokens,cfg,option):
    candidate=address(state,region,tokens,cfg,option)
    option['combination_ref']=candidate['combination_ref']
    row={'kind':'STRUCTURAL_PARTITION_CANDIDATE',**candidate,'offered_payload':deepcopy(option)}
    state.syntax_trace.append(row)
    return row


def live(state,receipt):
    from .validation_graph import validate
    return validate('EXCLUSION',state,receipt)


def _live(state,receipt):
    from .validation_graph import request,source
    """Validate a negative CONFIRM receipt without invoking selected-proof logic."""
    from .partial_readings import retired_refs
    from .selection_domains import valid,fingerprint
    try:
        if receipt.get('kind')!='STRUCTURAL_PARTITION_EXCLUSION':return False
        if receipt.get('exclusion_ref')!='partition-exclusion:'+digest({k:v for k,v in receipt.items() if k!='exclusion_ref'}):return False
        candidate=receipt['candidate'];payload=candidate['offered_payload'];condition=candidate['condition']
        core={k:v for k,v in candidate.items() if k not in {'kind','combination_ref','offered_payload'}}
        if candidate['combination_ref']!='partition-combination:'+digest(core):return False
        if payload.get('combination_ref')!=candidate['combination_ref'] or semantic(payload)!=candidate['proposal']:return False
        if (candidate['source_uid']!=state.source_uid or candidate['interpretation_version']!=state.interpretation_version
            or candidate['basis']['source_basis']!=source(state)
            or candidate['basis']['context_version']!=state.context_version):return False
        if condition and not (yield request('CONDITION',state,condition)):return False
        retired=retired_refs(state.syntax_trace)
        domain=next((r for r in reversed(state.syntax_trace) if r.get('kind')=='TASK_DOMAIN'
                     and r.get('task_ref')==receipt['domain_ref']),None)
        if domain is None or receipt['domain_ref'] in retired or not valid(state,domain,retired):return False
        if any(domain.get(k)!=v for k,v in {'slot':'structural_partition','selection_purpose':SelectionPurpose.CONFIRM.value,
            'candidate_ids':['PARTITION'],'supported_ids':[],
            'task_outcome':'NONE_FIT_IN_ENUMERATED_GENERATOR','branch_condition':condition,
            'execution_basis':candidate['basis'],'source_range':candidate['source_range'],
            'token_refs':candidate['token_refs']}.items()):return False
        if domain.get('prerequisites',[])!=receipt['prerequisites']:return False
        pages=domain['page_evidence']
        if len(pages)!=1 or pages!=receipt['pages']:return False
        page=pages[0];key=page['decision_ref'];decision=state.decisions.get(key)
        if (page['outcome']!='NONE_FIT' or page['candidate_ids']!=['PARTITION']
            or page['candidate_payloads']!={'PARTITION':digest(payload)}
            or decision is None or decision.slot_id!='structural_partition'
            or decision.selector_outcome!='NONE_FIT' or decision.selected
            or fingerprint(state,key)!=page['fingerprint']):return False
        row=next((r for r in reversed(state.syntax_trace) if r.get('kind')=='STRUCTURAL_TASK'
                  and r.get('decision_ref')==key),None)
        if (row is None or row.get('alternatives')!=[payload] or row.get('branch_condition')!=condition
            or row.get('execution_basis')!=candidate['basis'] or row.get('selection_purpose')!=SelectionPurpose.CONFIRM.value
            or row.get('region_ref')!=candidate['region_ref']
            or row.get('prerequisites',[])!=receipt['prerequisites']):return False
        for premise in domain.get('prerequisites',()):
            prior=state.decisions.get(premise['proof'].get('decision_ref'))
            if (prior is None or prior.slot_id!=premise['slot'] or digest(premise['value'])!=premise['proof'].get('payload_hash')
                or not (yield request('PROOF',state,premise['proof'],_branch=condition))):return False
        return True
    except (KeyError,TypeError,ValueError):return False


def record(state,candidate,domain):
    receipt={'kind':'STRUCTURAL_PARTITION_EXCLUSION','candidate':deepcopy(candidate),
        'domain_ref':domain['task_ref'],'pages':deepcopy(domain['page_evidence']),
        'prerequisites':deepcopy(domain.get('prerequisites',[]))}
    receipt['exclusion_ref']='partition-exclusion:'+digest(receipt)
    if not live(state,receipt):return None
    state.syntax_trace.append(receipt)
    return receipt


def read(state,receipt):
    result=live(state,receipt)
    from .dispatch_evidence import observe
    observe(state,'PARTITION_EXCLUSION',receipt,result)
    return result


def applicable(state,receipt,region,tokens,cfg,relation):
    candidate=receipt['candidate'];condition=active(state)
    return (candidate['region_ref']==region.region_id and candidate['token_refs']==[t.token_id for t in tokens]
        and candidate['proposal']['relation']==relation and candidate['basis']==execution_basis(state,cfg)
        and candidate['condition']==(condition.record() if condition else None) and read(state,receipt))


def find(state,candidate):
    for row in reversed(state.syntax_trace):
        if row.get('kind')=='STRUCTURAL_PARTITION_EXCLUSION' and row['candidate']['combination_ref']==candidate['combination_ref']:
            if read(state,row):return row
    return None


def failure_receipt(state,failure):
    witness=failure.get('witness',{});ref=witness.get('exclusion_ref')
    receipt=next((r for r in reversed(state.syntax_trace)
                 if r.get('kind')=='STRUCTURAL_PARTITION_EXCLUSION' and r.get('exclusion_ref')==ref),None)
    if receipt is None:return None
    candidate=receipt['candidate']
    if (failure.get('category')!='PARTITION_REJECTED' or failure.get('region_ref')!=candidate['region_ref']
        or failure.get('source_range')!=candidate['source_range']
        or witness.get('proposal')!=candidate['offered_payload']
        or witness.get('combination_ref')!=candidate['combination_ref']
        or witness.get('rejection_domain_ref')!=receipt['domain_ref']
        or failure.get('owner_proof')!=candidate['offered_payload'].get('relation_proof')):return None
    return receipt


def failure_live(state,failure):
    receipt=failure_receipt(state,failure)
    return receipt is not None and read(state,receipt)
