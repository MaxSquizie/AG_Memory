"""Addressed membership for a source connector; lexical readings come later."""
from copy import deepcopy
from .structural_tasks import choose,source_set,licensed
from .probe_prerequisites import accepted
from .source_collections import valid


def select(state,release,selector,region,tokens,cfg,spans):
    from .component_nominal_groups import merge_groups
    groups=[]
    for lo,hi in spans:
        markers=[t.token_id for t in tokens if lo<=t.start and t.end<=hi]
        if not markers:
            state.diag('NOMINAL_COORDINATION_MARKER_UNRESOLVED',region.region_id)
            return False
        wording='«'+state.text[lo:hi]+'» at '+str([lo,hi])
        scope=choose(state,release,selector,region,cfg,'nominal_coordination_scope',[
            {'candidate_id':'NOMINAL','marker_refs':markers,
             'label':wording+' joins participants together in ONE nominal slot, preserving distinct members'},
            {'candidate_id':'OTHER','marker_refs':markers,
             'label':wording+' does not join participants in one nominal slot; it has another function or scope'}],
            'What does this exact connector join? Modifiers may stand between it and participant heads. '
            'Matching case or proximity alone does not establish the relation. Do not resolve lexical readings.')
        if not scope:return False
        if scope[0]['candidate_id']=='OTHER':return None
        begin=len(state.syntax_trace)
        selected=source_set(state,release,selector,region,tokens,cfg,'nominal_coordination_members',
            'For '+wording+', select the head occurrence of EVERY participant in this same nominal group. '
            'Include all coordinated members, even when separated by descriptions. Select heads only; '
            'leave their modifiers and other clauses outside this set. Equal spelling does not mean equal identity. '
            'This choice neither establishes case nor merges the participants into one entity.',
            exclude=markers,admissible=lambda members:len(members)>=2,
            prerequisites=(accepted('nominal_coordination_scope',scope),))
        if not selected:return False
        members,proofs=selected
        receipt=next((row for row in reversed(state.syntax_trace[begin:]) if row.get('kind')=='SOURCE_SET'),None)
        if receipt is None or not valid(state,receipt) or len(members)<2:return False
        refs=[t.token_id for t in members]
        # Preserve the existing contextual-reading producer after membership
        # selection; it offers readings, never prunes source membership.
        from itertools import combinations
        from .contextual_name_case import resolve
        contextual=[]
        for left,right in combinations(members,2):
            av=[v for v in left.variants if v.pos in {'NOUN','NPRO'}]
            bv=[v for v in right.variants if v.pos in {'NOUN','NPRO'}]
            if av and bv and not any(a.cases & b.cases for a in av for b in bv):
                contextual.extend(resolve(state,release,selector,region,left,right,cfg) or [])
        if set(receipt['selected_refs'])!=set(refs):return False
        # Morphology is not a closed domain here. The clause consumer must
        # establish actual nominal readings and their joint case/role validity.
        groups.append({'member_refs':refs,'marker_refs':markers,'cases':None,
                       'operator':'AND','contextual_readings':contextual,
                       'source_evidence':[{'scope_proof':scope[1],'marker_refs':markers,
                                           'collection':deepcopy(receipt)}]})
    merged=merge_groups(groups)
    if merged is None or not all(live(state,g) for g in merged):return False
    state.syntax_trace.append({'kind':'NOMINAL_COORDINATION','region_ref':region.region_id,
                               'groups':deepcopy(merged),'selected':'NOMINAL','task_outcome':'SUPPORTED'})
    return merged


def live(state,group):
    evidence=group.get('source_evidence')
    if evidence is None:return True  # Legacy producer has its separate contract.
    if not evidence or group.get('operator')!='AND':return False
    members=set();markers=set()
    for row in evidence:
        collection=row['collection'];refs=row['marker_refs']
        if (not licensed(state,row['scope_proof'],marker_refs=refs)
                or row['scope_proof'].get('candidate_id')!='NOMINAL' or not valid(state,collection)
                or len(collection['selected_refs'])<2 or set(refs)!=set(collection['excluded_refs'])):return False
        members.update(collection['selected_refs']);markers.update(refs)
    return members==set(group['member_refs']) and markers==set(group['marker_refs']) and not members&markers
