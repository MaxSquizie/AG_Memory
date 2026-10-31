"""Typed external reads for run-local composition tasks; not a second store."""


def observe(state,kind,value,expected=True):
    from .composition_session import current
    runtime=current(state)
    if runtime is not None:runtime.dispatcher.observe(kind,value,expected)


def valid(state,kind,value):
    if kind=='PARTITION_EXCLUSION':
        from .partition_exclusions import live
        return live(state,value)
    if kind=='CONDITIONAL_PROOF':
        from .structural_conditions import historical
        from .structural_tasks import _licensed
        return historical(state,value['condition']) and _licensed(state,value['proof'],
            _branch=value['condition'],**value['expected_payload'])
    if kind=='REFINEMENT_HOST':
        from .refinement_host_proof import live
        return live(state,value)
    if kind=='CONSTRAINT_SET':
        from .component_constraints import constraint_signature
        return constraint_signature(state,value['region_ref'],value['task_scope'])==value['signature']
    if kind=='PROOF':
        from .structural_tasks import licensed
        return licensed(state,value['proof'],**value['expected_payload'])
    if kind=='INVENTORY_QUERY':
        from .function_inventory import live
        return any(r.get('inventory_kind')==value['kind'] and r.get('inventory_tokens')==value['refs']
            and r.get('inventory_signature')==value['signature'] and live(state,r) for r in state.syntax_trace)
    if kind=='INVENTORY':
        from .function_inventory import live
        row=next((r for r in reversed(state.syntax_trace) if r.get('kind')=='FUNCTION_INVENTORY'
            and r.get('inventory_ref')==value),None)
        return row is not None and live(state,row)
    if kind=='NOMINAL_HOST':
        from .component_constraints import host_live
        return host_live(state,value)
    raise ValueError('DISPATCH_EVIDENCE_KIND_UNKNOWN')


def probe_stamp(state,key):
    from .partial_readings import retired_refs
    from .selection_domains import fingerprint
    if key in retired_refs(state.syntax_trace):return None
    return fingerprint(state,key)
