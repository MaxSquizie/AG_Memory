"""Addressed open relation alternatives, before structural shell expansion.

Domain membership is evidence for considering a hypothesis, never evidence for
asserting it. These receipts deliberately cannot serve as scalar task proofs or
closed partial-composition receipts. No branch execution is implemented here.
"""
from copy import deepcopy
from .canonical_ledger import digest
from .composition_dispatcher import canonical
from .partial_readings import valid_domain


def retain(state,region,tokens,request,cfg,domain):
    membership=domain.record()
    if not valid_domain(state,membership):raise ValueError('STRUCTURAL_DOMAIN_UNGROUNDED')
    from .composition_session import current
    runtime=current(state)
    context=canonical({'request':request,'constraints':cfg.get('_task_constraints'),
        'constraints_text':cfg.get('_task_constraints_text'),
        'ownership_feedback':cfg.get('_ownership_feedback'),
        'parent_feedback':runtime.tasks.feedback if runtime else None,
        'memory_context':runtime.context_signature() if runtime else None,
        'morphology_scope':runtime.morphology_scope if runtime else None,
        'domain_feedback':runtime.domain_feedback if runtime else None})
    address={'source_uid':state.source_uid,'region_ref':region.region_id,
        'source_range':list(region.source_range),'token_refs':[t.token_id for t in tokens],
        'input_scope':runtime.input_signature() if runtime else None,'context':context}
    forest_ref='structural-forest:'+digest(address)
    hypotheses=[]
    # Sort for order-independent addresses and snapshots, never for preference.
    for value in sorted(domain.values,key=lambda v:v['candidate_id']):
        ref=forest_ref+':'+digest(value)
        hypotheses.append({'hypothesis_ref':ref,'candidate':deepcopy(value),
            'membership_ref':domain.domain_ref,'status':'OPEN',
            'obligations':[{'kind':'STRUCTURAL_SHELL_UNEXPANDED','hypothesis_ref':ref}],
            'structure_complete':False,'write_eligible':False})
    row={'kind':'STRUCTURAL_OPEN_DOMAIN','forest_ref':forest_ref,**address,
        'interpretation_version':state.interpretation_version,
        'membership':membership,'hypotheses':hypotheses,
        # This closes only the supplied relation menu, not its partitions or
        # the language domain. No empty frontier can be inferred from it.
        'relation_menu_complete':True,'producer_complete':False,
        'frontier_complete':False,'propagation_complete':False,
        'structure_complete':False,'write_eligible':False}
    row['receipt_digest']=digest(row)
    if not live(state,row):raise ValueError('STRUCTURAL_DOMAIN_ADDRESS_MISMATCH')
    if row not in state.syntax_trace:state.syntax_trace.append(deepcopy(row))
    return deepcopy(row)


def live(state,row):
    from .validation_graph import validate
    result=validate('FOREST',state,row)
    from .dispatch_evidence import observe
    observe(state,'STRUCTURAL_FOREST',row,result)
    return result


def _live(state,row):
    from .validation_graph import request
    """Check immutable evidence, not structural readiness or current area match."""
    payload={k:v for k,v in row.items() if k!='receipt_digest'}
    if not (row.get('kind')=='STRUCTURAL_OPEN_DOMAIN'
        and row.get('receipt_digest')==digest(payload)
        and row.get('source_uid')==state.source_uid
        and row.get('interpretation_version')==state.interpretation_version
        and (yield request('DOMAIN',state,row.get('membership',{})))):return False
    membership=row['membership']
    receipt=next((r for r in reversed(state.syntax_trace)
        if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref')==membership['domain_ref']),None)
    if not receipt or receipt.get('slot')!='structural_relation':return False
    if any(receipt.get(k)!=row.get(k) for k in ('source_range','token_refs')):return False
    address={k:row[k] for k in ('source_uid','region_ref','source_range','token_refs','input_scope','context')}
    if row['forest_ref']!='structural-forest:'+digest(address):return False
    values=sorted(membership['alternatives'],key=lambda v:v['candidate_id'])
    if [h.get('candidate') for h in row['hypotheses']]!=values:return False
    for h,value in zip(row['hypotheses'],values):
        if any(value.get(k)!=row[k] for k in ('source_uid','region_ref','token_refs','input_scope')):return False
        if h.get('membership_ref')!=membership['domain_ref']:return False
        if h.get('hypothesis_ref')!=row['forest_ref']+':'+digest(value):return False
    return True


def current_domains(state):
    """Latest receipt per addressed input; superseded evidence stays diagnostic."""
    latest={r['forest_ref']:r for r in state.syntax_trace
            if r.get('kind')=='STRUCTURAL_OPEN_DOMAIN'}
    return [deepcopy(r) for r in latest.values() if live(state,r)]
