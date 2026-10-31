"""Typed external reads for run-local composition tasks; not a second store."""


def observe(state,kind,value,expected=True):
    from .composition_session import current
    runtime=current(state)
    if runtime is not None:runtime.dispatcher.observe(kind,value,expected)


def valid(state,kind,value):
    if kind in {'READING_DOMAIN','STRUCTURAL_FOREST'}:
        from .validation_graph import validate
        return validate('DOMAIN' if kind=='READING_DOMAIN' else 'FOREST',state,value)
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


def evidence_probe_refs(state,kind,value):
    """Addresses an explicitly replaced assumption; no validation or observers."""
    if kind in {'NOMINAL_HOST','REFINEMENT_HOST'}:return {value['decision_ref']}
    domains={r['task_ref']:r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN'}
    def include_packet(packet):
        latest={r['task_ref']:r for r in packet.get('trace',()) if r.get('kind')=='TASK_DOMAIN'}
        for ref,row in latest.items():domains.setdefault(ref,row)
    pending=[];refs=set();seen=set()
    if kind in {'PROOF','CONDITIONAL_PROOF'}:
        pending.append(('proof',value.get('proof')))
        if kind=='CONDITIONAL_PROOF':pending.append(('condition',value.get('condition')))
    elif kind=='READING_DOMAIN':pending.append(('proof',value))
    elif kind=='STRUCTURAL_FOREST':pending.append(('proof',value.get('membership')))
    elif kind=='PARTITION_EXCLUSION':
        pending.append(('domain',value.get('domain_ref')))
        pending.append(('condition',value.get('candidate',{}).get('condition')))
        refs.update(p['decision_ref'] for p in value.get('pages',()))
    else:return refs
    while pending:
        typ,item=pending.pop()
        if item is None:continue
        if typ=='proof':
            if not isinstance(item,dict):continue
            if item.get('decision_ref'):refs.add(item['decision_ref'])
            pending.append(('domain',item.get('domain_ref')))
            continue
        key=item if typ=='domain' else item.get('condition_ref')
        if (typ,key) in seen:continue
        seen.add((typ,key))
        if typ=='domain':
            refs.add(key);row=domains.get(key,{})
            refs.update(row.get('page_refs',()))
            pending.extend(('proof',p.get('proof')) for p in row.get('prerequisites',()))
            pending.append(('condition',row.get('branch_condition')))
        else:
            node=state.observation.get('structural_condition_registry',{}).get(key,{})
            include_packet(state.observation.get('structural_condition_evidence',{}).get(key,{}))
            pending.append(('proof',node.get('forest',{}).get('membership')))
            parent=node.get('parent_condition_ref')
            if parent:pending.append(('condition',{'condition_ref':parent}))
            shell=state.observation.get('structural_shell_registry',{}).get(node.get('parent_shell_ref'),{})
            include_packet(shell.get('evidence',{}))
            pending.extend(('domain',row.get('task_ref')) for row in shell.get('dependencies',()))
            pending.append(('proof',shell.get('partition_proof')))
    return refs
