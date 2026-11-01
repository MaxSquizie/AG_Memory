"""Typed external reads for run-local composition tasks; not a second store."""


KINDS=frozenset({
    'MORPHOLOGY_PROVENANCE','MORPHOLOGY_ORIGINAL','READING_QUERY','READING_USE',
    'READING_DECISION','BUNDLE_CONSTRAINTS','READING_DOMAIN','STRUCTURAL_FOREST',
    'PARTITION_EXCLUSION','CONDITIONAL_PROOF','REFINEMENT_HOST','CONSTRAINT_SET',
    'PROOF','INVENTORY_QUERY','INVENTORY','INVENTORY_UNIT','NOMINAL_HOST','RECOVERY_QUERY',
})


DIRECT_QUERIES=frozenset({'CONSTRAINT_SET','READING_QUERY','RECOVERY_QUERY','INVENTORY_QUERY'})

def observation_address(kind,value,expected=True):
    """Only direct addressed queries supersede their own previous snapshots.

    Exact witness assessments stay cumulative. Cached child obligations are
    frozen separately and never enter this chronological direct-read map.
    """
    from copy import deepcopy
    if kind not in KINDS:raise ValueError('DISPATCH_EVIDENCE_KIND_UNKNOWN')
    address=deepcopy(value)
    if kind in {'CONSTRAINT_SET','READING_QUERY','RECOVERY_QUERY'}:address.pop('signature',None)
    if kind in DIRECT_QUERIES:return address
    return [address,expected]


def read_record(state,kind,value,expected=True):
    """Freeze ancestry at consumption, before a repair replaces current rows."""
    from copy import deepcopy
    return {'kind':kind,'value':deepcopy(value),'expected':expected,
            'probe_refs':sorted(evidence_probe_refs(state,kind,value))}


def retain_read(previous,current):
    if previous and current['kind'] not in DIRECT_QUERIES:
        current['probe_refs']=sorted(set(previous.get('probe_refs',())) | set(current['probe_refs']))
    return current


def read_probe_refs(state,read):
    # Preserve consumed ancestry AND dependencies used by current replay.
    # Example: ORIGINAL can acquire a recovery publication as its live source
    # projection while its requested original reading stays unchanged.
    return set(read.get('probe_refs',())) | evidence_probe_refs(state,read['kind'],read['value'])


def observe(state,kind,value,expected=True):
    from .composition_session import current
    runtime=current(state)
    if runtime is not None:runtime.dispatcher.observe(kind,value,expected)


def valid(state,kind,value,*,provider_results=None):
    if kind=='RECOVERY_QUERY':
        from .recovery_constraints import inspect,signature
        return signature(inspect(state,value['token_refs'],value.get('condition')))==value['signature']
    if kind=='MORPHOLOGY_PROVENANCE':
        from .morphology_provenance import _live
        return _live(state,value['row'],provider_results)
    if kind=='MORPHOLOGY_ORIGINAL':
        from .morphology_provenance import _original
        return _original(state,value['token_ref'],value['reading'])
    if kind=='READING_QUERY':
        from .reading_producers import query_snapshot
        return query_snapshot(state,value['token_ref'],value.get('scope'),value.get('reading'))==value['signature']
    if kind=='READING_USE':
        from .reading_producers import restore
        from .reading_producers import evaluate
        from .composition_dispatcher import canonical
        w=restore(value['witness'])
        return canonical(evaluate(state,w,value.get('condition'),value.get('scope'),value.get('transfer'),provider_results))==value['assessment']
    if kind=='READING_DECISION':
        from .reading_decisions import inspect
        return inspect(state,value['decision_ref'],value.get('condition'))['stamp']==value['stamp']
    if kind=='BUNDLE_CONSTRAINTS':
        from .bundle_constraints import inspect,signature
        from .state import FrameCandidate
        return signature(inspect(state,value['region_ref'],value['task_scope'],value['token_refs'],
            [FrameCandidate(**f) for f in value['frames']],value.get('condition'),nominal=value['nominal'],require_nominal_projection=value.get('require_nominal_projection',False)))==value['signature']
    if kind in {'READING_DOMAIN','STRUCTURAL_FOREST'}:
        from .validation_graph import validate
        return validate('DOMAIN' if kind=='READING_DOMAIN' else 'FOREST',state,value)
    if kind=='PARTITION_EXCLUSION':
        from .partition_exclusions import live
        return live(state,value)
    if kind=='CONDITIONAL_PROOF':
        from .structural_conditions import historical
        from .structural_tasks import _licensed
        return (value.get('condition') is None or historical(state,value['condition'])) and _licensed(state,value['proof'],
            _branch=value['condition'],**value['expected_payload'])
    if kind=='REFINEMENT_HOST':
        from .refinement_host_proof import live
        return live(state,value)
    if kind=='CONSTRAINT_SET':
        from .structural_conditions import historical
        if value.get('condition') is not None and not historical(state,value['condition']):return False
        from .component_constraints import constraint_signature
        return constraint_signature(state,value['region_ref'],value['task_scope'],value.get('condition'))==value['signature']
    if kind=='PROOF':
        from .structural_tasks import licensed
        return licensed(state,value['proof'],**value['expected_payload'])
    if kind=='INVENTORY_UNIT':
        from .function_inventory import _unit_live
        return _unit_live(state,value['unit'],condition=value.get('condition'))
    if kind=='INVENTORY_QUERY':
        from .function_inventory import live
        return any(r.get('inventory_kind')==value['kind'] and r.get('inventory_tokens')==value['refs']
            and r.get('inventory_signature')==value['signature'] and live(state,r,condition=value.get('condition')) for r in state.syntax_trace)
    if kind=='INVENTORY':
        from .function_inventory import live
        ref=value.get('inventory_ref') if isinstance(value,dict) else value
        condition=value.get('condition') if isinstance(value,dict) else None
        row=next((r for r in reversed(state.syntax_trace) if r.get('kind')=='FUNCTION_INVENTORY'
            and r.get('inventory_ref')==ref),None)
        return row is not None and live(state,row,condition=condition)
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
    from .evidence_ancestry import collect
    return collect(state,lambda:_evidence_probe_refs(state,kind,value))


def _evidence_probe_refs(state,kind,value):
    """Addresses an explicitly replaced assumption; no validation or observers."""
    if kind not in KINDS:raise ValueError('DISPATCH_EVIDENCE_KIND_UNKNOWN')
    if kind=='RECOVERY_QUERY':
        from .recovery_constraints import probe_refs
        return probe_refs(state,value['token_refs'],value.get('condition'))
    if kind=='INVENTORY_UNIT':
        return evidence_probe_refs(state,'INVENTORY',{'inventory_ref':value['unit'].get('inventory_ref'),
            'condition':value.get('condition')})
    if kind=='MORPHOLOGY_ORIGINAL':
        from .morphology_provenance import probe_refs
        return set().union(*(probe_refs(state,r) for r in state.syntax_trace
            if r.get('kind')=='MORPHOLOGY_PUBLICATION' and r.get('token_ref')==value['token_ref']))
    if kind=='MORPHOLOGY_PROVENANCE':
        from .morphology_provenance import probe_refs
        return probe_refs(state,value['row'])
    if kind=='READING_QUERY':
        from .reading_producers import query_refs
        return query_refs(state,value['token_ref'],value.get('scope'),value.get('reading'))
    if kind=='READING_USE':
        import json
        w=value['witness'];proof=json.loads(w['proof_json']) or json.loads(w['domain_json'])
        refs=evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':proof,'condition':json.loads(w['address']['condition_json'])})
        for parent in (json.loads(w['payload_json']) or {}).get('reading_parent_proofs',()):
            refs.update(evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':parent,'condition':value.get('condition')}))
        if value.get('transfer'):
            from .morphology_provenance import probe_refs
            for row in value['transfer'].values():refs.update(probe_refs(state,row))
        return refs
    if kind=='READING_DECISION':
        refs={value['decision_ref']}
        required=state.component_probe_records.get(value['decision_ref'],{}).get('branch_condition')
        refs.update(evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':None,'condition':required}))
        refs.update(evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':value.get('proof'),'condition':value.get('condition')}))
        return refs
    if kind=='BUNDLE_CONSTRAINTS':
        from .bundle_constraints import select_records,required_inventory_refs
        from .state import FrameCandidate
        refs=evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':None,'condition':value.get('condition')})
        for row in select_records(state,value['region_ref'],value['task_scope'],value.get('condition')):
            refs.update(evidence_probe_refs(state,'READING_DOMAIN',row) if row['kind']=='PARTIAL_READING_DOMAIN'
                else evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':row['proof'],'condition':value.get('condition')}))
        if value['nominal']:
            frames=[FrameCandidate(**f) for f in value['frames']]
            for ref in required_inventory_refs(state,value['region_ref'],value['task_scope'],value['token_refs'],frames,value.get('condition')):
                refs.update(evidence_probe_refs(state,'INVENTORY',{'inventory_ref':ref,'condition':value.get('condition')}))
        return refs
    if kind=='NOMINAL_HOST':return {value['decision_ref']}
    if kind=='REFINEMENT_HOST':
        refs={value['decision_ref']}
        for proof in value.get('premises',()):
            refs.update(evidence_probe_refs(state,'PROOF',{'proof':proof}))
        return refs
    tasks={(r.get('decision_ref'),r.get('selected')):r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK'}
    domains={r['task_ref']:r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN'}
    def include_packet(packet):
        latest={r['task_ref']:r for r in packet.get('trace',()) if r.get('kind')=='TASK_DOMAIN'}
        for ref,row in latest.items():domains.setdefault(ref,row)
        selected={(r.get('decision_ref'),r.get('selected')):r for r in packet.get('trace',()) if r.get('kind')=='STRUCTURAL_TASK'}
        for ref,row in selected.items():tasks.setdefault(ref,row)
    pending=[];refs=set();seen=set()
    if kind in {'PROOF','CONDITIONAL_PROOF'}:
        pending.append(('proof',value.get('proof')))
        if kind=='CONDITIONAL_PROOF':pending.append(('condition',value.get('condition')))
    elif kind in {'INVENTORY','INVENTORY_QUERY'}:
        condition=value.get('condition') if isinstance(value,dict) else None
        pending.append(('condition',condition))
        if kind=='INVENTORY':
            ref=value.get('inventory_ref') if isinstance(value,dict) else value
            records=[r for r in state.syntax_trace if r.get('kind')=='FUNCTION_INVENTORY'
                     and r.get('inventory_ref')==ref]
        else:
            records=[r for r in state.syntax_trace if r.get('kind')=='FUNCTION_INVENTORY'
                     and r.get('inventory_kind')==value['kind'] and r.get('inventory_tokens')==value['refs']
                     and r.get('inventory_signature')==value['signature']]
        for row in records:
            pending.extend(('proof',p) for p in row.get('proofs',()))
            pending.append(('condition',row.get('branch_condition')))
    elif kind=='CONSTRAINT_SET':
        pending.append(('condition',value.get('condition')))
        for row in state.syntax_trace:
            if row.get('region_ref')!=value['region_ref'] or row.get('task_scope')!=value['task_scope']:continue
            if row.get('kind')=='ESTABLISHED_PREDICATE_ROLE':pending.append(('proof',row.get('proof')))
            elif row.get('kind')=='PARTIAL_READING_DOMAIN':pending.append(('proof',row))
            elif row.get('kind')=='NOMINAL_HOST_QUESTION' and row.get('decision_ref'):refs.add(row['decision_ref'])
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
            identity=(item.get('decision_ref'),item.get('candidate_id'))
            if ('proof',identity) in seen:continue
            seen.add(('proof',identity))
            if item.get('decision_ref'):refs.add(item['decision_ref'])
            row=tasks.get(identity,{})
            pending.extend(('proof',p.get('proof')) for p in row.get('prerequisites',()))
            pending.append(('condition',row.get('branch_condition')))
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
