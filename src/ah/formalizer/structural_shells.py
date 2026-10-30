"""Isolated conditional AND/OR partition production; no child execution or IR."""
from copy import deepcopy
from dataclasses import asdict,replace
from .canonical_ledger import digest
from .composition_dispatcher import canonical,DispatchBlocked
from .composition_tree import InputSlot
from .structural_conditions import branch,applicable


def execution_order(forest):
    """Deterministic traversal only; ordering never excludes a hypothesis."""
    return iter(forest['hypotheses'])


def produce(state,release,selector,region,tokens,cfg,request,forest):
    from .composition_session import current,session
    from .partition_domain import PartitionDomain
    from .relation_partitions import binary
    parent=current(state)
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
        reader=parent.reader.fork(hypothesis['hypothesis_ref']) if parent.reader else None
        local=deepcopy(state);local.budget=state.budget
        begin=len(local.syntax_trace);diagnostics_begin=len(local.diagnostics)
        old_decisions=set(local.decisions);old_probes=set(local.component_probe_records)
        selected=None;condition=None
        with session(local,release,reader,selector,parent.morph) as runtime:
            runtime.original=deepcopy(parent.original)
            runtime.restore_context(parent.capture_context())
            runtime.tasks.feedback=deepcopy(parent.tasks.feedback)
            runtime.dispatcher.limit=max(0,parent.dispatcher.limit-parent.dispatcher.spent)
            try:
                with branch(local,forest,hypothesis,cfg) as condition:
                    proof={'condition':condition.record(),'hypothesis_ref':condition.hypothesis_ref}
                    selected=PartitionDomain(local,release,selector,region,tokens,cfg,kind,proof).resolve(binary)
            except DispatchBlocked:
                # Budget/cycle is unfinished work, never rejection of a member.
                pass
            finally:parent.dispatcher.spent+=runtime.dispatcher.spent
        if condition is None:continue
        row={'kind':'STRUCTURAL_CONDITIONAL_SHELL','hypothesis_ref':hypothesis['hypothesis_ref'],
            'forest_ref':forest['forest_ref'],'relation':kind,'condition':condition.record(),
            'source_range':list(region.source_range),'token_refs':[t.token_id for t in tokens],
            'status':'OPEN','children':[],'partition_proof':None,
            'producer_complete':False,'structure_complete':False,'write_eligible':False,
            'obligations':[{'kind':'PARTITION_DOMAIN_UNENUMERATED'}]}
        if selected:
            proposal,partition=selected
            row.update(status='SHELL_PRODUCED',partition_proof=deepcopy(partition[1]),
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
        row['receipt_digest']=digest(row)
        state.syntax_trace.append(row);results.append(deepcopy(row))
    return results


def evidence_state(state,shell):
    """Rebuild a read-only validation view; never merge conditional facts."""
    from .state import Decision,Ground
    local=deepcopy(state);evidence=shell['evidence']
    for key,raw in evidence['decisions'].items():
        raw=deepcopy(raw);raw['grounds']=[Ground(**g) for g in raw['grounds']]
        local.decisions.setdefault(key,Decision(**raw))
    for key,record in evidence['probes'].items():local.component_probe_records.setdefault(key,deepcopy(record))
    local.syntax_trace=deepcopy(evidence['trace'])+local.syntax_trace
    return local


def live(state,shell):
    """Historical shell evidence, not write eligibility or current applicability."""
    from .structural_conditions import historical
    from .structural_tasks import _licensed
    if shell.get('receipt_digest')!=digest({k:v for k,v in shell.items() if k!='receipt_digest'}):return False
    if not historical(state,shell['condition']):return False
    if shell['status']!='SHELL_PRODUCED':return False
    condition=shell['condition'];forest=condition['forest']
    if (shell['hypothesis_ref']!=condition['hypothesis_ref'] or shell['forest_ref']!=forest['forest_ref']
            or shell['relation']!=condition['candidate']['relation'] or len(shell['children'])!=2):return False
    slot=deepcopy(forest['context']['request']) or canonical(InputSlot())
    slot['surrounding_relations']=[*slot['surrounding_relations'],shell['relation']]
    for index,child in enumerate(shell['children']):
        if child['input_slot']!=slot or child['inherited_context']!=forest['context']:return False
        if child['child_ref']!='structural-child:'+digest([shell['hypothesis_ref'],shell['partition_proof'],
                index,child['token_refs'],slot]):return False
    local=evidence_state(state,shell)
    from .selection_domains import valid as enumeration_live
    from .partial_readings import retired_refs
    retired=retired_refs(local.syntax_trace)
    if not shell['dependencies'] or not all(r['task_ref'] not in retired and enumeration_live(local,r,retired)
        and r.get('branch_condition')==shell['condition'] for r in shell['dependencies']):return False
    if not _licensed(local,shell['partition_proof'],_branch=shell['condition'],relation=shell['relation']):return False
    # The partition's selected payload must match every materialized child slot.
    return _licensed(local,shell['partition_proof'],_branch=shell['condition'],
        operands=[c['token_refs'] for c in shell['children']],marker_refs=shell['marker_refs'],
        shared_material=shell['shared_material'])
