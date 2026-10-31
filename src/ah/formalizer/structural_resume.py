"""Resume only resource-stopped work; preserve actual answers and spent budget."""
from copy import deepcopy
from .canonical_ledger import digest

RESOURCE_CODES={'COMPOSITION_DISPATCH_INCOMPLETE','COMPUTATION_LIMIT','STRUCTURAL_TASK_SEARCH_INCOMPLETE'}


def resource_stamp(runtime,cfg):
    b=runtime.state.budget
    return digest([runtime.dispatcher.limit,b.llm_limit,b.probe_scope_limits,
        runtime.release.entries('ProposalPolicy')[0].get('max_rule_steps'),
        cfg.get('context_chars'),cfg.get('max_candidates')])


def synchronize(source,target):
    """Current authoritative proofs override saved branch snapshots."""
    if source is target:return
    target.decisions.update(deepcopy(source.decisions))
    target.component_probe_records.update(deepcopy(source.component_probe_records))
    def identity(row):
        kind=row.get('kind')
        if kind=='TASK_DOMAIN':return kind,row.get('task_ref')
        if kind=='STRUCTURAL_TASK':return kind,row.get('decision_ref'),row.get('selected')
        return kind,digest(row)
    latest={identity(r):r for r in target.syntax_trace}
    authoritative={identity(r):r for r in source.syntax_trace if r.get('kind') in
        {'DEPENDENCY_REJECTED','COMPOSITION_PROBE_SUPERSEDED','TASK_DOMAIN','STRUCTURAL_TASK'}}
    for key,event in authoritative.items():
        if latest.get(key)!=event:target.syntax_trace.append(deepcopy(event))


def reopen(runtime):
    state=runtime.state
    stopped={d.detail for d in state.diagnostics if d.code=='COMPUTATION_LIMIT'}
    for key in stopped:
        record=state.component_probe_records.get(key)
        if record and record['decision'].get('selector_outcome') is None:
            state.component_probe_records.pop(key,None)
            runtime.dispatcher.invalidate('probe:'+key,'RESOURCE_AVAILABLE')
    for key,node in list(runtime.dispatcher.nodes.items()):
        if (node.get('receipt',{}).get('task_outcome')=='INCOMPLETE'
                or any(d.code in RESOURCE_CODES for d in node.get('diagnostics',()))):
            runtime.dispatcher.invalidate(key,'RESOURCE_AVAILABLE')
    state.diagnostics[:]=[d for d in state.diagnostics if d.code not in RESOURCE_CODES]
    for task in runtime.structural_shell_tasks.values():
        if task.get('result') and task['result']['status']=='OPEN':
            reopen(task['runtime']);task['diagnostics_begin']=len(task['state'].diagnostics)
