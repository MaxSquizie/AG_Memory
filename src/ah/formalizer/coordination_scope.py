"""Closed local/shared modifier scopes over an already composed conjunction."""
from copy import deepcopy
from .canonical_ledger import digest


def install(choice, selected, all_frames, region, decision):
    """Only the selected root is assertible; its operands remain structural."""
    for frame in selected:
        if frame.frame_id in choice.get('temporal_assignments',{}):
            frame.semantic['explicit_region']=deepcopy(choice['temporal_assignments'][frame.frame_id])
            # Distinct existential witnesses, even when period expressions agree.
            frame.semantic['time_scope_owner']=frame.frame_id
            frame.semantic['temporal_scope_decision']=decision
    if not choice['wrappers']:
        for f in selected:
            f.semantic['operator_forest'] = [choice['tree']]
            f.semantic['coordination_decision'] = decision
        return
    for f in choice['wrappers']:
        f.semantic['coordination_decision'] = decision
    # Other local roots keep coordination_owner and cannot escape as facts.
    # No AND_ELIMINATION applies through an unlicensed lexical modifier.
    root = choice['wrappers'][-1]
    root.semantic.pop('coordination_owner', None)
    all_frames.extend(choice['wrappers'])


def trace(choices):
    return [{'candidate_id':c['candidate_id'],'label':c['label'],'tree':c['tree'],
             'lifted_modifier_refs':c['lifted_modifier_refs'],
             'temporal_assignments':c.get('temporal_assignments',{}),
             'wrappers':[{'frame_id':f.frame_id,'proposition_args':f.semantic['proposition_args'],
                          'source_frame':f.semantic['scope_source_frame']} for f in c['wrappers']]}
            for c in choices]
