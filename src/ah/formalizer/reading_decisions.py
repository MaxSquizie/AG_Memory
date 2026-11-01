"""Liveness of decisions used by derived morphology, separate from use support.

This does not prove that a selected payload licenses a particular reading.
Typed payload-to-reading witnesses remain the responsibility of its producer.
"""
from .canonical_ledger import digest
from .composition_dispatcher import canonical
from .selection_evidence import selected_candidate


def inspect(state,key,condition=None):
    from .partial_readings import retired_refs
    from .structural_conditions import historical,allows
    decision=state.decisions.get(key)
    record=state.component_probe_records.get(key)
    selected=selected_candidate(decision)
    retired=key in retired_refs(state.syntax_trace)
    if record and record.get('superseded_by'):retired=True
    required=record.get('branch_condition') if record else None
    if required is not None and (condition is None or not allows(state,required,condition)):retired=True
    tasks=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK'
           and r.get('decision_ref')==key and r.get('selected')==selected]
    proof=None
    if selected is not None and tasks:
        task=tasks[-1]
        proof={k:task.get(k) for k in ('domain_ref','payload_hash','selection_purpose')}
        proof.update(decision_ref=key,candidate_id=selected)
        # Task refs are domain refs in current structural selection records.
        proof['domain_ref']=proof['domain_ref'] or key
        from .structural_tasks import _licensed
        if not _licensed(state,proof,_branch=condition):retired=True
    if condition is not None and not historical(state,condition):retired=True
    # Include selection evidence, not mutable consumer validation/history.
    payload=None if decision is None else [decision.slot_id,decision.candidates,decision.selected,
        decision.selector_outcome,[(g.type,g.text,g.value) for g in decision.grounds]]
    stamp=digest(canonical([state.source_uid,state.interpretation_version,state.text,
        payload,record,retired,condition,proof,None if retired else selected]))
    return {'selected':None if retired else selected,'stamp':stamp,'proof':proof}


def selected(state,key):
    from .function_inventory import execution_condition
    condition=execution_condition(state)
    result=inspect(state,key,condition)
    from .dispatch_evidence import observe
    observe(state,'READING_DECISION',{'decision_ref':key,'condition':condition,
        'stamp':result['stamp'],'proof':result['proof']})
    return result['selected']


def receipt(state,key):
    from .function_inventory import execution_condition
    condition=execution_condition(state)
    result=inspect(state,key,condition)
    if result['selected'] is None:raise ValueError('READING_DECISION_UNSUPPORTED')
    return {'decision_ref':key,'condition':condition,'stamp':result['stamp'],'proof':result['proof']}


def receipt_live(state,value):
    result=inspect(state,value['decision_ref'],value.get('condition'))
    from .dispatch_evidence import observe
    live=result['stamp']==value['stamp'] and result['selected'] is not None
    observe(state,'READING_DECISION',value,live)
    return live
