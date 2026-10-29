"""Proof-carrying noun-group identity. Resolved identity is separate from a mention-local unknown referent."""
from .canonical_ledger import digest


def payload(state, unit):
    constraint=unit.get('reference_constraint')
    if constraint is None:
        return None
    mention=unit['mention_ref']
    binding=state.observation.get('nominal_reference_bindings',{}).get(mention)
    if binding is None:
        return None  # A typed placeholder preserves the source relation, not identity.
    from .selection_evidence import selected_candidate
    from .reference_structure import signature
    read=state.observation.get('nominal_reference_reads',{}).get(binding['interpretation_decision_ref'],{})
    if (not read or read.get('search_incomplete') or digest(read)!=binding.get('reference_domain_hash')
            or signature(state)!=binding.get('structure_signature')):
        raise ValueError('NOMINAL_REFERENCE_DOMAIN_STALE')
    decision=state.decisions.get(binding['interpretation_decision_ref'])
    if (selected_candidate(decision)!=binding.get('selected_candidate_id')
            or not binding.get('selected_candidate_id')
            or digest(constraint)!=digest(binding.get('reference_constraint'))):
        raise ValueError('NOMINAL_REFERENCE_SELECTION_STALE')
    if binding.get('local_spatial_anchor'):
        from .nominal_reference_local import rows
        if not any(r['memory_binding_ref']==binding['anchor_binding_ref']
                   and digest(r['local_spatial_anchor'])==digest(binding['local_spatial_anchor'])
                   for r in rows(state,constraint)):
            raise ValueError('NOMINAL_REFERENCE_LOCAL_ANCHOR_STALE')
    else:
        read=state.observation.get('nominal_reference_reads',{}).get(binding['interpretation_decision_ref'],{})
        if (not read or read.get('search_incomplete') or read.get('context_read_hash')!=binding.get('context_read_hash')
                or not any(r['entity_ref']==binding['target_ref'] and r['memory_binding_ref']==binding['anchor_binding_ref']
                           for r in read.get('rows',()))):
            raise ValueError('NOMINAL_REFERENCE_READ_STALE')
    return {'binding_kind':'NOMINAL_REFERENCE',**binding}


def validate(p, ledger, journal, store=None):
    if p.get('binding_kind')!='NOMINAL_REFERENCE':
        return
    anchor=p.get('anchor_binding_ref')
    proof=ledger.data['bindings'].get(anchor,{})
    # A new reference only points backwards into a previously durable binding;
    # it cannot create a self-supporting identity cycle within this transaction.
    if (not anchor or proof.get('target_ref')!=p['target_ref'] or
            not ledger.binding_live(anchor,ledger.paths()) or journal is None):
        raise ValueError('NOMINAL_REFERENCE_GROUND_INVALID')
    local=p.get('local_spatial_anchor')
    if local is not None:
        meta=store.get_element_any_domain(p['target_ref']).meta.get('relative_place') if store else None
        expected={k:v for k,v in local.items() if k!='entity_ref'}
        if (meta!=expected or local.get('entity_ref')!=p['target_ref']
                or local.get('source_tag')!=p['source_tag'] or proof.get('source_tag')!=p['source_tag']
                or proof.get('binding_kind')!='SPATIAL_ANCHOR'
                or local['anchor_ref'] in set(p['reference_constraint'].get('anchor_refs',()))|{p['reference_constraint']['head_ref']}
                or p.get('context_read_hash') or p.get('premise_support_refs')):
            raise ValueError('NOMINAL_REFERENCE_LOCAL_ANCHOR_INVALID')
        return
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
            # Morphology evidence contains tuples in memory and JSON lists in
            # durable receipts. Compare the complete canonical value, not the
            # incidental Python container representation.
            digest(request.get('constraint'))==digest(p.get('reference_constraint')) and
            log['result_hash']==p.get('context_read_hash')==digest(result) and
            result.get('scope')=='ACTIVE_WORKSPACE' and not result.get('search_incomplete') and
            any(r.get('entity_ref')==p['target_ref'] and r.get('memory_binding_ref')==anchor
                and set(p.get('premise_support_refs',()))<=set(r.get('premise_support_refs',()))
                for r in result['rows'])):
            return
    raise ValueError('NOMINAL_REFERENCE_RECEIPT_INVALID')
