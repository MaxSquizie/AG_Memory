"""Previously introduced local spatial referents, independent of coordinates."""
from copy import deepcopy
from .canonical_ledger import digest


def rows(state,constraint):
    # A destination in this very clause must not become its own antecedent.
    from .regions import reference_goal
    from .component_policy import rejected
    boundary=reference_goal(state,constraint['head_ref'])['source_range'][0]
    result={}
    for frame in state.frames:
        d=state.decisions.get(frame.frame_id+'|predicate_value')
        if not d or d.outcome!='RESOLVED' or len(d.selected)!=1 or frame.semantic.get('structural_unresolved') or rejected(state,frame):continue
        spec=frame.semantic.get('candidate_specs',{}).get(d.selected[0],{})
        for slot in frame.semantic.get('spatial_slots',{}).values():
            place=slot.get('selected_place')
            if (not place or slot['rule']['kind']!='ANCHOR' or slot['rule']['sense_id']!=spec.get('sense_id')
                    or frame.source_range[1]>boundary):continue
            mid=place['entity_ref'];tag=place['source_tag']
            anchor='binding:place:'+digest([tag,place['anchor_ref'],place['rule_id'],mid])
            lo,hi=frame.source_range
            result[mid]={'entity_ref':mid,'memory_binding_ref':anchor,'source_tag':tag,
                'premise_support_refs':[],'features':[],'reference_kind':'PLACE',
                'label':'Previously introduced relative place; coordinates UNKNOWN; source excerpt: '+state.text[lo:hi],
                'local_spatial_anchor':deepcopy(place)}
    return list(result.values())
