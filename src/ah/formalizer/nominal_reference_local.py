"""Established source spatial referents, independent of position or coordinates."""
from copy import deepcopy
from .canonical_ledger import digest


def rows(state,constraint):
    # Source order does not establish identity. Only the same occurrence is
    # excluded; distinct anchors in this clause or later remain candidates.
    from .component_policy import rejected
    own=set(constraint.get('anchor_refs',()))|{constraint['head_ref']}
    result={}
    for frame in state.frames:
        d=state.decisions.get(frame.frame_id+'|predicate_value')
        if not d or d.outcome!='RESOLVED' or len(d.selected)!=1 or frame.semantic.get('structural_unresolved') or rejected(state,frame):continue
        spec=frame.semantic.get('candidate_specs',{}).get(d.selected[0],{})
        from .function_inventory import frame_live
        from .component_constraints import frame_hosts_live
        if not spec or not frame_live(state,frame) or not frame_hosts_live(state,frame):continue
        for slot in frame.semantic.get('spatial_slots',{}).values():
            if slot['rule']['sense_id']!=spec.get('sense_id') and not slot['rule'].get('generic'):continue
            place=slot.get('selected_place')
            if not place or slot['rule']['kind']!='ANCHOR' or place['anchor_ref'] in own:continue
            mid=place['entity_ref'];tag=place['source_tag']
            anchor='binding:place:'+digest([tag,place['anchor_ref'],place['rule_id'],mid])
            lo,hi=frame.source_range
            result[mid]={'entity_ref':mid,'memory_binding_ref':anchor,'source_tag':tag,
                'premise_support_refs':[],'features':[],'reference_kind':'PLACE',
                'label':'Established source relative place; coordinates UNKNOWN; source excerpt: '+state.text[lo:hi],
                'local_anchor_ref':place['anchor_ref'],'local_spatial_anchor':deepcopy(place)}
    return list(result.values())
