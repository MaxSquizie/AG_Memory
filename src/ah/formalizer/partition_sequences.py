"""Reconsider source ownership when a later part has no accepted first piece.

An exhausted restricted domain identifies a dependency, not the guilty choice.
Only a source-supported repair choice permits retiring an earlier assignment.
"""
from .canonical_ledger import digest


def select_parts(domain,roles,select):
    from .composition_contracts import record_failure
    from .composition_session import current
    from .component_probe_replay import supersede
    from .structural_tasks import choose
    from .relation_composition import RELATIONS
    from .composition_dispatcher import canonical
    state=domain.state;runtime=current(state)
    groups=[];starts=[];proofs=[];attempts=set();feedback=''
    original_cfg=domain.cfg
    local_cfg={k:v for k,v in original_cfg.items() if k not in {'_task_constraints','_task_constraints_text','_ownership_feedback'}}
    try:
        while len(groups)<len(roles):
            index=len(groups);begin=len(state.syntax_trace)
            domain.cfg={**(local_cfg if feedback else original_cfg),'_ownership_feedback':feedback}
            chosen=select(index,groups)
            if chosen:
                starts.append(begin);groups.append(chosen[0]);proofs.append(chosen[1]);continue
            exhausted=next((r for r in reversed(state.syntax_trace[begin:])
                if r.get('kind')=='SOURCE_SPAN_EXHAUSTED' and r['region_ref']==domain.region.region_id),None)
            if not exhausted or not groups:return None
            available=set(exhausted['available_refs'])
            parents=[j for j,g in enumerate(groups) if any(t.token_id not in available for t in g)]
            if not parents:return None
            signature=digest(canonical([domain.region.region_id,domain.kind,
                runtime.input_signature() if runtime else None,
                runtime.context_signature() if runtime else None,
                [[t.token_id for t in g] for g in groups],index,exhausted['available_refs'],domain.constraints]))
            if signature in attempts:
                state.diag('STRUCTURAL_REVISION_NO_PROGRESS',domain.region.region_id)
                return None
            attempts.add(signature)
            if len(attempts)>original_cfg.get('refinement',{}).get('max_depth',16):
                state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE',domain.region.region_id)
                return None
            failure=record_failure(state,domain.region,'OWNERSHIP_DOMAIN_BLOCKED',domain.proof,
                'No first piece was accepted for '+roles[index]+' under earlier source assignments. '
                'This does not prove which earlier assignment is wrong, or exhaust all partitions.',
                {'blocked_role':roles[index],'restricted_search':exhausted,
                 'assignments':[{'role':roles[j],'token_refs':[t.token_id for t in groups[j]],
                                 'proofs':list(proofs[j])} for j in parents]},search_complete=False)
            end=len(state.syntax_trace)
            options=[{'candidate_id':str(j),'part_index':j,
                'token_refs':[t.token_id for t in groups[j]],
                'label':'Reconsider '+roles[j]+': «'+' '.join(t.span for t in groups[j])+'»'} for j in parents]
            remaining=' '.join(t.span for t in domain.tokens if t.token_id in available)
            repair=choose(state,domain.release,domain.selector,domain.region,local_cfg,
                'structural_ownership_revision',options,
                'Current outer relation: '+RELATIONS[domain.kind]+'. No accepted '+roles[index]+
                ' could be built from the still available words «'+remaining+'». '
                'Earlier assignments exclude their words from this part. Which assignment below contains '
                'words that the SOURCE places in the missing part and therefore needs reconsideration? '
                'Select the assignment to reconsider NEXT; multiple numbers are alternative next repairs, not a joint change. '
                'Failure alone is not evidence that an assignment is wrong. '
                '0: no listed assignment is shown wrong by the source; ?: insufficient evidence.')
            if not repair:
                state.diag('PARTITION_OWNERSHIP_UNRESOLVED',domain.region.region_id)
                return None
            target=repair[0]['part_index'];replacement=repair[1]['decision_ref']
            refs={r['decision_ref'] for r in state.syntax_trace[starts[target]:end]
                  if r.get('kind')=='STRUCTURAL_TASK' and r.get('region_ref')==domain.region.region_id
                  and r.get('decision_ref')}
            for ref in refs:supersede(state,ref,replacement)
            if runtime:
                keys={'probe:'+ref for ref in refs if 'probe:'+ref in runtime.dispatcher.nodes}
                runtime.dispatcher.discard_reads(keys,'SOURCE_OWNERSHIP_REVISED')
                for key in keys:runtime.dispatcher.invalidate(key,'SOURCE_OWNERSHIP_REVISED')
            feedback=('Reconsider '+roles[target]+' previously selected as «'+' '.join(t.span for t in groups[target])+
                '». That assignment left no accepted '+roles[index]+' in «'+remaining+
                '». A source-based repair selected this assignment for revision. '
                'Select its source words again; keep other established roles and the outer relation.')
            state.syntax_trace.append({'kind':'PARTITION_OWNERSHIP_REVISED','region_ref':domain.region.region_id,
                'failure_ref':failure['failure_ref'],'revision_proof':repair[1],
                'revised_role':roles[target],'preserved_roles':roles[:target],
                'retired_refs':sorted(refs),'relation_proof':domain.proof})
            del groups[target:];del starts[target:];del proofs[target:]
        return groups
    finally:domain.cfg=original_cfg
