"""Isolated conditional AND/OR partition production; no child execution or IR."""
from copy import deepcopy,copy
from dataclasses import asdict,replace
from .canonical_ledger import digest
from .composition_dispatcher import canonical,DispatchBlocked
from .composition_tree import InputSlot
from .structural_conditions import branch,applicable,resolve,inherit_scope,registry


def execution_order(forest):
    """Deterministic traversal only; ordering never excludes a hypothesis."""
    return iter(forest['hypotheses'])


def produce(state,release,selector,region,tokens,cfg,request,forest):
    from .composition_session import current,CompositionSession,activate
    from .partition_domain import PartitionDomain
    from .relation_partitions import binary
    parent=current(state)
    from .structural_conditions import active
    inherited=active(state)
    if parent is None or not applicable(state,forest,cfg):return []
    results=[]
    # Each producer gets a private state and dispatcher. Only resource use is
    # shared; conditional choices, revisions, diagnostics and frames cannot leak.
    for hypothesis in execution_order(forest):
        kind=hypothesis['candidate']['relation']
        if kind not in {'AND','OR'}:
            state.syntax_trace.append({'kind':'STRUCTURAL_SHELL_PENDING',
                'hypothesis_ref':hypothesis['hypothesis_ref'],'reason':'RELATION_PRODUCER_NOT_CONNECTED',
                'structure_complete':False,'write_eligible':False})
            continue
        if parent.reader is not None and not callable(getattr(parent.reader,'fork',None)):
            state.syntax_trace.append({'kind':'STRUCTURAL_SHELL_PENDING',
                'hypothesis_ref':hypothesis['hypothesis_ref'],'reason':'CONTEXT_READER_FORK_UNAVAILABLE',
                'structure_complete':False,'write_eligible':False})
            continue
        task_key=digest([hypothesis['hypothesis_ref'],forest['receipt_digest']])
        task=parent.structural_shell_tasks.get(task_key)
        if task is None:
            reader=parent.reader.fork(hypothesis['hypothesis_ref']) if parent.reader else None
            local=deepcopy(state);local.budget=state.budget
            runtime=CompositionSession(local,release,reader,selector,parent.morph)
            runtime.original=deepcopy(parent.original)
            runtime.restore_context(parent.capture_context())
            runtime.tasks.feedback=deepcopy(parent.tasks.feedback)
            runtime.structural_child_edge=getattr(parent,'structural_child_edge',None)
            task={'state':local,'runtime':runtime,'begin':len(local.syntax_trace),
                'diagnostics_begin':len(local.diagnostics),'old_decisions':set(local.decisions),
                'old_probes':set(local.component_probe_records),'result':None}
            parent.structural_shell_tasks[task_key]=task
        local=task['state'];runtime=task['runtime']
        from .structural_resume import synchronize
        synchronize(state,local)
        # Latest external invalidations take precedence over a suspended branch.
        for event in state.syntax_trace:
            if event.get('kind') in {'DEPENDENCY_REJECTED','COMPOSITION_PROBE_SUPERSEDED'} and event not in local.syntax_trace:
                local.syntax_trace.append(deepcopy(event))
        local.observation.setdefault('structural_condition_registry',{}).update(deepcopy(registry(state)))
        for name in ('structural_condition_evidence','structural_shell_registry'):
            local.observation.setdefault(name,{}).update(deepcopy(state.observation.get(name,{})))
        if task['result'] is not None and live(state,task['result']):
            results.append(deepcopy(task['result']));continue
        begin=task['begin'];diagnostics_begin=task['diagnostics_begin']
        old_decisions=task['old_decisions'];old_probes=task['old_probes']
        selected=None;condition=None;spent_before=runtime.dispatcher.spent
        with activate(runtime):
            runtime.dispatcher.limit=spent_before+max(0,parent.dispatcher.limit-parent.dispatcher.spent)
            try:
                with inherit_scope(state,local,cfg,inherited), branch(local,forest,hypothesis,cfg) as condition:
                    proof={'condition':condition.record(),'hypothesis_ref':condition.hypothesis_ref}
                    selected=PartitionDomain(local,release,selector,region,tokens,cfg,kind,proof).resolve(binary)
            except DispatchBlocked:
                pass
            finally:parent.dispatcher.spent+=runtime.dispatcher.spent-spent_before
        if condition is None:continue
        registry(state).update(deepcopy(registry(local)))
        state.observation.setdefault('structural_condition_evidence',{}).update(
            deepcopy(local.observation.get('structural_condition_evidence',{})))
        row={'kind':'STRUCTURAL_CONDITIONAL_SHELL','hypothesis_ref':hypothesis['hypothesis_ref'],
            'forest_ref':forest['forest_ref'],'relation':kind,'condition':condition.record(),
            'source_range':list(region.source_range),'token_refs':[t.token_id for t in tokens],
            'status':'OPEN','children':[],'partition_proof':None,
            'producer_complete':False,'structure_complete':False,'write_eligible':False,
            'obligations':[{'kind':'PARTITION_DOMAIN_UNENUMERATED'}]}
        if selected:
            proposal,partition=selected
            selected_row=next(r for r in reversed(local.syntax_trace) if r.get('kind')=='STRUCTURAL_TASK'
                and r.get('decision_ref')==partition[1]['decision_ref'])
            combination=next(v['combination_ref'] for v in selected_row['alternatives'] if v['candidate_id']=='PARTITION')
            row.update(status='SHELL_PRODUCED',combination_ref=combination,partition_proof=deepcopy(partition[1]),
                marker_refs=[t.token_id for t in partition[0]],shared_material=deepcopy(proposal.shared_material))
            slot=request or InputSlot()
            slot=replace(slot,surrounding_relations=(*slot.surrounding_relations,kind))
            for index,group in enumerate(proposal.groups):
                refs=[t.token_id for t in group]
                row['children'].append({'child_ref':'structural-child:'+digest([
                    hypothesis['hypothesis_ref'],partition[1],index,refs,canonical(slot)]),
                    'token_refs':refs,'input_slot':canonical(slot),
                    'inherited_context':deepcopy(forest['context']),
                    'status':'UNEXPANDED','structure_complete':False,'write_eligible':False})
            row['obligations'] += [{'kind':'CHILD_UNEXPANDED','child_ref':c['child_ref']} for c in row['children']]
        else:row['obligations'].append({'kind':'PARTITION_PRODUCTION_PENDING'})
        # Conditional evidence is nested, not merged into globally selectable
        # state. Each record keeps enough provenance for inspection and replay.
        row['evidence']={'trace':deepcopy(local.syntax_trace[begin:]),
            'decisions':{k:asdict(v) for k,v in local.decisions.items() if k not in old_decisions},
            'probes':{k:deepcopy(v) for k,v in local.component_probe_records.items() if k not in old_probes},
            'diagnostics':[asdict(d) for d in local.diagnostics[diagnostics_begin:]],
            'context_reads':deepcopy(local.context_reads[len(state.context_reads):])}
        from .selection_domains import valid as enumeration_live
        from .partial_readings import retired_refs
        retired=retired_refs(local.syntax_trace)
        row['dependencies']=[deepcopy(r) for r in local.syntax_trace[begin:]
            if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref') not in retired
            and enumeration_live(local,r,retired)]
        row['shell_ref']='structural-shell:'+digest([row['hypothesis_ref'],row['partition_proof'],row['condition']])
        row['receipt_digest']=digest(row)
        if row not in state.syntax_trace:state.syntax_trace.append(row)
        results.append(deepcopy(row));task['result']=deepcopy(row)
        state.observation.setdefault('structural_shell_registry',{})[row['shell_ref']]=deepcopy(row)
    return results


def evidence_state(state,shell,*,read_only=False):
    """Rebuild a read-only validation view; never merge conditional facts."""
    from .state import Decision,Ground
    local=copy(state) if read_only else deepcopy(state);evidence=shell['evidence']
    if read_only:
        local.decisions=dict(state.decisions);local.component_probe_records=dict(state.component_probe_records)
    for key,raw in evidence['decisions'].items():
        raw=deepcopy(raw);raw['grounds']=[Ground(**g) for g in raw['grounds']]
        local.decisions.setdefault(key,Decision(**raw))
    for key,record in evidence['probes'].items():local.component_probe_records.setdefault(key,deepcopy(record))
    local.syntax_trace=deepcopy(evidence['trace'])+local.syntax_trace
    return local


def live(state,shell):
    from .validation_graph import validate
    return validate('SHELL',state,shell)


def _live(state,shell):
    """Historical shell evidence, not write eligibility or current applicability."""
    if shell.get('receipt_digest')!=digest({k:v for k,v in shell.items() if k!='receipt_digest'}):return False
    from .validation_graph import request,overlay
    if not (yield request('CONDITION',state,shell['condition'])):return False
    if shell['status']!='SHELL_PRODUCED':return False
    condition=resolve(state,shell['condition']);forest=condition.forest
    if (shell['hypothesis_ref']!=condition.hypothesis_ref or shell['forest_ref']!=forest['forest_ref']
            or shell['relation']!=condition.candidate['relation'] or len(shell['children'])!=2):return False
    slot=deepcopy(forest['context']['request']) or canonical(InputSlot())
    slot['surrounding_relations']=[*slot['surrounding_relations'],shell['relation']]
    for index,child in enumerate(shell['children']):
        if child['input_slot']!=slot or child['inherited_context']!=forest['context']:return False
        if child['child_ref']!='structural-child:'+digest([shell['hypothesis_ref'],shell['partition_proof'],
                index,child['token_refs'],slot]):return False
    local=overlay(state,shell['evidence'])
    from .selection_domains import valid as enumeration_live
    from .partial_readings import retired_refs
    retired=retired_refs(local.syntax_trace)
    if not shell['dependencies'] or not all(r['task_ref'] not in retired and enumeration_live(local,r,retired)
        and r.get('branch_condition')==shell['condition'] for r in shell['dependencies']):return False
    # One exact selected-proof obligation; expected fields are part of its key.
    return (yield request('PROOF',local,shell['partition_proof'],_branch=shell['condition'],
        relation=shell['relation'],combination_ref=shell.get('combination_ref'),
        operands=[c['token_refs'] for c in shell['children']],marker_refs=shell['marker_refs'],
        shared_material=shell['shared_material']))
