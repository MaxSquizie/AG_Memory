"""Addressed membership for a source connector; lexical readings come later."""
from copy import deepcopy
from .structural_tasks import choose,source_set,licensed
from .probe_prerequisites import accepted
from .source_collections import valid


def live(state,group,*,collecting=False):
    evidence=group.get('source_evidence')
    if evidence is None:return True  # Legacy producer has its separate contract.
    if not evidence or group.get('operator')!='AND':return False
    completion=group.get('coordination_completion')
    if not collecting and any(r.get('membership_first') for r in evidence) and completion is None:return False
    if completion is not None and (completion.get('candidate_id')!='DONE' or not licensed(state,completion)):return False
    members=set();markers=set()
    for row in evidence:
        collection=row['collection'];refs=row['marker_refs']
        if row.get('membership_first'):
            if (not licensed(state,row['scope_proof']) or row['scope_proof'].get('candidate_id')!='NOMINAL'
                    or not valid(state,collection) or len(collection['selected_refs'])<2
                    or collection['excluded_refs'] or not licensed(state,row['marking_proof'])):return False
            marking=row['marking_proof']['candidate_id'];marker_collection=row.get('marker_collection')
            if marking=='NONE':
                if refs or marker_collection is not None:return False
            elif marking=='SOURCE':
                if (marker_collection is None or not valid(state,marker_collection)
                        or set(marker_collection['selected_refs'])!=set(refs)
                        or set(marker_collection['excluded_refs'])!=set(collection['selected_refs'])):return False
            else:return False
        elif (not licensed(state,row['scope_proof'],marker_refs=refs)
                or row['scope_proof'].get('candidate_id')!='NOMINAL' or not valid(state,collection)
                or len(collection['selected_refs'])<2 or set(refs)!=set(collection['excluded_refs'])):return False
        members.update(collection['selected_refs']);markers.update(refs)
    return members==set(group['member_refs']) and markers==set(group['marker_refs']) and not members&markers


def discover(state,release,selector,region,tokens,cfg):
    """Discover flat joint participants independently of lexical markers."""
    from .task_contracts import SelectionPurpose
    from .probe_prerequisites import from_proof
    groups=[];prior=();seen=set()
    while True:
        established='; '.join('«'+' '.join(t.span for t in tokens if t.token_id in g['member_refs'])+'»'
                             for g in groups) or 'none'
        scope=choose(state,release,selector,region,cfg,'nominal_coordination_discovery',[
            {'candidate_id':'NOMINAL','label':'Another flat group of distinct participants jointly fills ONE nominal slot; its members can have descriptions and no conjunction need be written'},
            {'candidate_id':'COMPLEX','label':'A remaining nominal group contains alternatives or nested groups whose grouping affects the meaning; flattening it into joint participants would lose that meaning'}],
            'Find the first remaining coordinated nominal group in this target. Already collected groups: '+established+'. '
            'Different roles of one predicate, a nominal with its modifiers, and several descriptions of ONE entity are not a coordinated group. '
            'Propositional coordination is handled by the outer relation. 0 means no further nominal group; ? means undecidable.',
            empty={'candidate_id':'DONE','label':'no further nominal coordination in this target'},
            purpose=SelectionPurpose.NEXT,prerequisites=prior)
        if not scope:return False
        if scope[0]['candidate_id']=='DONE':
            for group in groups:group['coordination_completion']=scope[1]
            if not all(live(state,g) for g in groups):return False
            state.syntax_trace.append({'kind':'NOMINAL_COORDINATION','region_ref':region.region_id,
                'groups':deepcopy(groups),'completion_proof':scope[1],'task_outcome':'SUPPORTED'})
            return groups
        if scope[0]['candidate_id']=='COMPLEX':
            state.diag('NOMINAL_COORDINATION_STRUCTURE_UNSUPPORTED',region.region_id)
            return False
        if len(groups)>=cfg['max_candidates']:
            state.diag('NOMINAL_COORDINATION_SEARCH_INCOMPLETE',region.region_id)
            return False
        begin=len(state.syntax_trace)
        selected=source_set(state,release,selector,region,tokens,cfg,'nominal_coordination_members',
            'Select the head occurrence of EVERY participant of this ONE remaining flat nominal group. '
            'Include all joint members, even with intervening descriptions or no written conjunction. '
            'Select heads only, not their modifiers or connectors. Equal spelling does not establish identity.',
            admissible=lambda members:len(members)>=2,
            prerequisites=(accepted('nominal_coordination_discovery',scope),))
        if not selected:return False
        members,proofs=selected;refs=[t.token_id for t in members]
        collection=next((r for r in reversed(state.syntax_trace[begin:]) if r.get('kind')=='SOURCE_SET'),None)
        if collection is None or not valid(state,collection):return False
        signature=frozenset(refs)
        if signature in seen:
            state.diag('NOMINAL_COORDINATION_NO_PROGRESS',region.region_id);return False
        if any(signature & set(g['member_refs']) for g in groups):
            state.diag('NOMINAL_COORDINATION_STRUCTURE_UNSUPPORTED',region.region_id);return False
        seen.add(signature)
        premise=tuple(from_proof(state,p) for p in proofs)
        wording='«'+' '.join(t.span for t in members)+'»'
        mode=choose(state,release,selector,region,cfg,'nominal_coordination_marking',[
            {'candidate_id':'SOURCE','label':'This group has explicit coordinating words or delimiters outside its participant heads'},
            {'candidate_id':'NONE','label':'This group has no separate coordinating words or delimiters'}],
            'How is the established joint group '+wording+' linked in this source? Do not select descriptive words as connectors.',
            prerequisites=premise)
        if not mode:return False
        marker_collection=None;markers=[];marker_proofs=[]
        if mode[0]['candidate_id']=='SOURCE':
            begin=len(state.syntax_trace)
            material=source_set(state,release,selector,region,tokens,cfg,'nominal_coordination_markers',
                'Select all coordinating words or delimiters belonging to '+wording+' only. '
                'Exclude participant heads, their modifiers and other relations.',exclude=refs,
                prerequisites=(*premise,accepted('nominal_coordination_marking',mode)))
            if not material:return False
            markers=[t.token_id for t in material[0]];marker_proofs=material[1]
            marker_collection=next((r for r in reversed(state.syntax_trace[begin:]) if r.get('kind')=='SOURCE_SET'),None)
            if marker_collection is None or not valid(state,marker_collection):return False
        from itertools import combinations
        from .contextual_name_case import resolve
        contextual=[]
        for left,right in combinations(members,2):
            av=[v for v in left.variants if v.pos in {'NOUN','NPRO'}]
            bv=[v for v in right.variants if v.pos in {'NOUN','NPRO'}]
            if av and bv and not any(a.cases & b.cases for a in av for b in bv):
                contextual.extend(resolve(state,release,selector,region,left,right,cfg) or [])
        group={'member_refs':refs,'marker_refs':markers,'cases':None,'operator':'AND',
               'contextual_readings':contextual,'source_evidence':[{
                   'membership_first':True,'scope_proof':scope[1],'collection':deepcopy(collection),
                   'marker_refs':markers,'marking_proof':mode[1],'marker_collection':deepcopy(marker_collection)}]}
        if not live(state,group,collecting=True):return False
        groups.append(group)
        prior=(*prior,accepted('nominal_coordination_discovery',scope),*premise,
               accepted('nominal_coordination_marking',mode),*(from_proof(state,p) for p in marker_proofs))
