"""A released temporal expression cannot simultaneously fill a bare ENTITY slot."""
import re
from .clock_ranges import boundary_spans


def reject_entity_overlap(state,release,frames):
    from .temporal_functions import owned_refs
    temporal=owned_refs(state)
    for frame in frames:
        overlap=temporal & set(frame.argument_token_refs)
        if overlap:
            frame.semantic['structural_unresolved']=True
            frame.semantic['structural_rejection']='TEMPORAL_TOKEN_AS_ENTITY'
            state.reject(frame.frame_id,'TEMPORAL_OWNERSHIP','Released time expression reused as ENTITY: '+str(sorted(overlap)))
