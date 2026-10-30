"""Addressed function evidence and source-supported revision of a blocked split."""
from .canonical_ledger import digest
from .structural_tasks import choose, licensed_in_scope as licensed


def proof_refs(state, proof):
    refs={proof['decision_ref'],proof.get('domain_ref',proof['decision_ref'])}
    for row in state.syntax_trace:
        if row.get('kind')=='TASK_DOMAIN' and row.get('task_ref')==proof.get('domain_ref'):
            refs.update(row.get('page_refs',()))
    return refs


def read_proof(state,proof,**expected):
    if not licensed(state,proof,**expected):return False
    from .composition_session import current
    runtime=current(state)
    if runtime:
        for ref in sorted(proof_refs(state,proof)):
            key='probe:'+ref
            if key in runtime.dispatcher.nodes:
                runtime.dispatcher.read(key,runtime.dispatcher.nodes[key]['revision'])
                runtime.tasks.record_probe(ref)
    return True


def revise(domain,begin):
    state=domain.state
    events=[r for r in state.syntax_trace[begin:] if r.get('region_ref')==domain.region.region_id
            and r.get('kind') in {'STRUCTURAL_TASK','SOURCE_SPAN_EXHAUSTED'}]
    if not events or events[-1].get('kind')!='SOURCE_SPAN_EXHAUSTED':return False
    failure=events[-1];excluded=set(failure['excluded_refs'])
    candidates=[]
    for constraint in domain.constraints:
        if constraint.proof:
            candidates.extend((ref,'RELATION',constraint.proof) for ref in constraint.token_refs if ref in excluded)
    candidates.extend((ref,'CONTENT',proof) for ref,proof in domain.markers.items() if ref in excluded)
    if not candidates:return False
    signature=digest([sorted(domain.required),sorted(domain.markers),failure['slot'],failure['available_refs']])
    if signature in domain.revisions:
        state.diag('STRUCTURAL_REVISION_NO_PROGRESS',domain.region.region_id);return False
    if len(domain.revisions)>=domain.cfg.get('refinement',{}).get('max_depth',16):
        state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE',domain.region.region_id);return False
    domain.revisions.add(signature)
    evidence={t.token_id:t for t in domain.tokens}
    from .relation_composition import RELATIONS
    alternatives=[]
    from .relation_markers import function_label
    for ref,role,proof in candidates:
        token=evidence[ref]
        alternatives.append({'candidate_id':role+':'+ref,'token_ref':ref,'new_role':role,
            'relation':domain.kind,'owner_ref':domain.owner_choice[0]['owner_ref'] if domain.owner_choice else None,
            'replaced_proof':proof,
            **({'marker_relation_ref':ref} if role=='RELATION' else {'marker_content_ref':ref}),
            'label':'Revise «'+token.span+'» @'+str(token.start)+': '+function_label(token,domain.kind,role,
                evidence.get(domain.owner_choice[0]['owner_ref']) if domain.owner_choice else None)})
    remaining=', '.join('«'+t.span+'» @'+str(t.start) for t in domain.tokens if t.token_id in failure['available_refs']) or 'none'
    result=choose(state,domain.release,domain.selector,domain.region,domain.cfg,'structural_marker_revision',alternatives,
        'Current outer relation: '+RELATIONS[domain.kind]+'. '
        'No first piece was accepted from the still available occurrences: '+remaining+'. '
        'The earlier function assignments below excluded their occurrences from that search. '
        'Does the ORIGINAL SOURCE support changing one of those assignments as shown? '
        'A failed search does not prove any assignment wrong or exhaust every possible parse. '
        'Select only a source-supported correction, not the correction that would merely let execution continue. '
        'Other established functions and the outer relation remain fixed. '
        '0 means no listed correction is supported; ? means insufficient evidence.')
    if not result:return False
    selected,proof=result;ref=selected['token_ref']
    from .partition_domain import ContentRequired
    if selected['new_role']=='RELATION':
        domain.constraints=[ContentRequired(tuple(r for r in c.token_refs if r!=ref),c.reason,c.proof)
                            for c in domain.constraints if set(c.token_refs)-{ref}]
        domain.markers[ref]=proof
    else:
        domain.markers.pop(ref)
        domain.constraints.append(ContentRequired((ref,),'EXPLICIT_FUNCTION_REVISION',proof))
    keep=set()
    for p in [*(c.proof for c in domain.constraints if c.proof),*domain.markers.values()]:
        keep.update(proof_refs(state,p))
    if domain.owner_choice:keep.update(proof_refs(state,domain.owner_choice[1]))
    previous={r['decision_ref'] for r in state.syntax_trace[domain.trace_begin:]
              if r.get('kind')=='STRUCTURAL_TASK' and r.get('region_ref')==domain.region.region_id
              and r.get('decision_ref')}-keep
    from .component_probe_replay import supersede
    from .composition_session import current
    runtime=current(state)
    for old in previous:supersede(state,old,proof['decision_ref'])
    if runtime:
        for old in previous:
            if 'probe:'+old in runtime.dispatcher.nodes:
                runtime.dispatcher.invalidate('probe:'+old,'PARTITION_FUNCTION_REVISED')
    state.syntax_trace.append({'kind':'PARTITION_FUNCTION_REVISED','region_ref':domain.region.region_id,
        'restricted_search':failure,'revision_proof':proof,'replaced_proof':selected['replaced_proof'],
        'token_ref':ref,'new_role':selected['new_role'],'retired_refs':sorted(previous)})
    domain.cfg={**domain.cfg,'_ownership_feedback':selected['label']+'. This source-supported correction replaces the earlier function assignment.'}
    return True
