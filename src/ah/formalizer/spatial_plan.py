"""Relative places use ordinary M and binding operations, without world coordinates."""
from .canonical_ledger import digest
from .spatial_references import for_sense


def emit_roles(frame, selected, tag, frag, roles, emit):
    slot = for_sense(frame,selected.get('sense_id'))
    if slot is None: return
    place = slot.get('selected_place')
    if place is None: raise ValueError('SPATIAL_REFERENCE_UNRESOLVED')
    role = slot['rule']['role_id']
    if role in roles: raise ValueError('ARGUMENT_CARDINALITY_UNRESOLVED')
    mid = place['entity_ref']
    meta = {k:v for k,v in place.items() if k!='entity_ref'}
    emit('ENSURE_ENTITY',{'uid':mid,'mention_ref':place['anchor_ref'],
                         'source_tag':tag,'relative_place':meta},frag)
    anchor_binding = 'binding:place:'+digest([tag,place['anchor_ref'],place['rule_id'],mid])
    # This is a structural referent grounded in the source occurrence, not an
    # assertion that the source movement occurred. Shared closure retains it
    # when another fragment still uses the referent.
    emit('SET_IDENTITY_BINDING',{'binding_id':anchor_binding,'binding_kind':'SPATIAL_ANCHOR',
         'mention_ref':place['anchor_ref'],'target_ref':mid,'source_tag':tag,
         'premise_support_refs':[]},frag)
    if slot['rule']['kind']=='REFERENCE':
        bid = 'binding:place-reference:'+digest([tag,slot['mention_ref'],mid,slot['decision_ref']])
        emit('SET_IDENTITY_BINDING',{'binding_id':bid,'binding_kind':'SPATIAL_REFERENCE',
             'mention_ref':slot['mention_ref'],'target_ref':mid,'source_tag':tag,
             'anchor_binding_ref':anchor_binding,'interpretation_decision_ref':slot['decision_ref'],
             'premise_support_refs':[]},frag)
    roles[role] = mid
