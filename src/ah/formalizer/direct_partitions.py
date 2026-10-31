"""Collect addressed siblings; cardinality follows source grouping, not a guess."""
from .probe_prerequisites import from_proof
from .structural_tasks import choose,licensed_in_scope
from .structural_probe_inputs import collection
from .task_contracts import SelectionPurpose


def collect(domain):
    from .partition_sequences import select_parts
    from .relation_composition import RELATIONS
    state=domain.state;tokens=domain.tokens
    initial=None;completion=None
    base=(from_proof(state,domain.proof),) if domain.proof.get('decision_ref') else ()
    def premises(proofs):
        return (*base,*(from_proof(state,p) for group in proofs for p in group))
    def described(groups):
        return '; '.join('«'+' '.join(t.span for t in g)+'»' for g in groups) or 'none'
    question=('Selected outer relation: '+RELATIONS[domain.kind]+'. '
        'Collect its direct content parts in this scope. A direct part is one sibling in this group. '
        'Keep a dependent clause, negation, modality or differently grouped relation INSIDE its owning part. '
        'Do not split a nested relation into siblings, and do not bundle siblings as first item plus the rest. '
        'Connecting words of this outer relation stay outside the parts. ')
    def select(index,groups,proofs):
        nonlocal initial
        start=initial;initial=None
        return domain.span(tokens,'structural_operand_'+str(index+1),
            question+'Already selected direct parts: '+described(groups)+'. '
            'Select one further direct content part, keeping those assignments. '
            'Prefer the earliest unassigned direct part; source order does not establish membership. '
            'Include all its own nested content, but not another sibling. '
            'Words expressed once for several alternatives may be assigned to one part here; '
            'their shared use is checked separately.',
            exclude=[t.token_id for g in groups for t in g],covered=[t.token_id for g in groups for t in g],
            remaining_parts=1 if index==0 else 0,open_parts=True,
            initial=start,fixed_initial=start is not None,prerequisites=premises(proofs))
    def more(groups,proofs):
        nonlocal initial,completion
        initial=None;completion=None
        used={t.token_id for g in groups for t in g};excluded=used|set(domain.markers)
        raw=[[t.token_id for t in g] for g in groups]
        value=choose(state,domain.release,domain.selector,domain.region,domain.cfg,'structural_group_next',[
            {'candidate_id':'start:'+t.token_id,'index':i,'token_ref':t.token_id,
             'label':'Another direct part begins at «'+t.span+'» @'+str(t.start)}
            for i,t in enumerate(tokens) if t.token_id not in excluded],
            question+'Established direct parts: '+described(groups)+'. '
            'Is there ANOTHER direct part of THIS SAME outer relation? Select its first occurrence. '
            'A word inside an already selected part, or belonging to a nested relation, is not a new sibling. '
            '0 rejects the displayed starts; only exhaustion of all starts can finish this group. '
            '? means the source does not decide. Several numbers are alternative next starts, not several simultaneous parts.',
            empty={'candidate_id':'DONE','relation':domain.kind,'raw_groups':raw,
                   'label':'No additional direct part belongs to this group; selected parts: '+described(groups)}
                  if domain.required<=used else None,
            source_selection=collection('START',tokens,exclude=excluded),
            prerequisites=premises(proofs),purpose=SelectionPurpose.NEXT)
        if value is None:return None
        if value[0]['candidate_id']=='DONE':
            completion={'raw_groups':raw,'completion_proof':value[1]};return False
        initial=value;return True
    groups=select_parts(domain,['a direct content part','another direct content part'],select,continuation=more)
    return (groups,completion) if groups is not None and completion is not None else None


def valid(state,grouping,kind,groups,markers,shared):
    """Exact per-child projection after separately proved marker/shared ownership."""
    if not isinstance(grouping,dict):return False
    raw=grouping.get('raw_groups',());proof=grouping.get('completion_proof',{})
    decision=state.decisions.get(proof.get('decision_ref'))
    if (kind not in {'AND','OR','XOR'} or len(raw)!=len(groups) or len(raw)<2
            or decision is None or decision.slot_id!='structural_group_next'
            or proof.get('candidate_id')!='DONE' or proof.get('selection_purpose')!=SelectionPurpose.NEXT.value
            or not licensed_in_scope(state,proof,relation=kind,raw_groups=raw)):return False
    seen=set()
    for before,after in zip(raw,groups):
        if not before or len(set(before))!=len(before) or seen.intersection(before):return False
        seen.update(before)
        if {t.token_id for t in after}!=(set(before)-set(markers))|set(shared):return False
    return True
