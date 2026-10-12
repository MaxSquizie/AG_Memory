"""Proof-carrying noun-group identity. No new M for an unresolved reference."""
from .canonical_ledger import digest


def payload(state, unit):
    constraint=unit.get('reference_constraint')
    if constraint is None:
        return None
    mention=unit['mention_ref']
    binding=state.observation.get('nominal_reference_bindings',{}).get(mention)
    if binding is None:
        raise ValueError('NOMINAL_REFERENCE_UNRESOLVED')
    return {'binding_kind':'NOMINAL_REFERENCE',**binding}


def validate(p, ledger, journal):
    if p.get('binding_kind')!='NOMINAL_REFERENCE':
        return
    anchor=p.get('anchor_binding_ref')
    proof=ledger.data['bindings'].get(anchor,{})
    # A new reference only points backwards into a previously durable binding;
    # it cannot create a self-supporting identity cycle within this transaction.
    if (not anchor or proof.get('target_ref')!=p['target_ref'] or
            not ledger.binding_live(anchor,ledger.paths()) or journal is None):
        raise ValueError('NOMINAL_REFERENCE_GROUND_INVALID')
    records=journal.scan_unprocessed(0,payload_kinds={'run_bind','CONTEXT_READ'})
    owners={r['payload']['owner'] for r in records if r['payload'].get('kind')=='run_bind'
            and [r['payload'].get('observation_id'),r['payload'].get('version')]==p['source_tag']}
    for record in records:
        log=record['payload']
        if log.get('kind')!='CONTEXT_READ' or record.get('run_id') not in owners:
            continue
        request,result=log['request'],log['result']
        if (request.get('kind')=='NOMINAL_REFERENCE' and
            request.get('decision_ref')==p.get('interpretation_decision_ref') and
            request.get('mention_ref')==p['mention_ref'] and
            request.get('constraint')==p.get('reference_constraint') and
            log['result_hash']==p.get('context_read_hash')==digest(result) and
            result.get('scope')=='ACTIVE_WORKSPACE' and not result.get('search_incomplete') and
            any(r.get('entity_ref')==p['target_ref'] and r.get('memory_binding_ref')==anchor
                and set(p.get('premise_support_refs',()))<=set(r.get('premise_support_refs',()))
                for r in result['rows'])):
            return
    raise ValueError('NOMINAL_REFERENCE_RECEIPT_INVALID')
