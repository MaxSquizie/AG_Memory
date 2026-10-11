"""A released temporal expression cannot simultaneously fill a bare ENTITY slot."""
import re
from .clock_ranges import boundary_spans


def reject_entity_overlap(state,release,frames):
    evidence={e.token_id:e for e in state.evidence}
    for frame in frames:
        lo,hi=frame.source_range;raw=state.text[lo:hi];temporal=set()
        for rule in release.entries('TemporalRules'):
            for m in re.finditer(rule['pattern'],raw,re.I):
                for a,b in boundary_spans(rule,m):
                    temporal.update(e.token_id for e in evidence.values() if lo+a<=e.start and e.end<=lo+b)
        overlap=temporal & set(frame.argument_token_refs)
        if overlap:
            frame.semantic['structural_unresolved']=True
            frame.semantic['structural_rejection']='TEMPORAL_TOKEN_AS_ENTITY'
            state.reject(frame.frame_id,'TEMPORAL_OWNERSHIP','Released time expression reused as ENTITY: '+str(sorted(overlap)))
