"""Keep an unresolved referent without asking the model to invent identity."""
from .state import Decision, Ground


def introduce_without_antecedent(state, gap):
    """Only the licensed anonymous placeholder, never a sole memory match.

    The caller has already frozen context reads and rejected incomplete search.
    This does not assert that the person is different from another person.
    """
    options=gap['options']
    if len(options)!=1 or options[0]['kind']!='ANONYMOUS': return None
    if gap.get('search_incomplete') or gap.get('license') not in {'SUBJECT_AGREEMENT','UNSPECIFIED_ENTITY'}:
        return None
    cid=options[0]['candidate_id']
    if cid!='new:'+gap['gap_id']: return None
    d=Decision('implicit_argument',gap['gap_id'],(cid,))
    d.selected,d.outcome,d.lifecycle=(cid,),'RESOLVED','PROVISIONAL'
    d.grounds.append(Ground('D','licensed omission; no antecedent candidate; anonymous placeholder, identity UNKNOWN',cid))
    d.history.append({'kind':'ANONYMOUS_INTRODUCTION','omission_license':gap['license'],
                      'identity_status':'UNKNOWN','distinctness_asserted':False})
    state.decisions[gap['gap_id']]=d
    return cid


def unresolved_group(state,gap):
    """A licensed plural role survives an unresolved identity question."""
    d=state.decisions.get(gap['gap_id'])
    if (gap.get('license')!='SUBJECT_AGREEMENT' or gap['features'].get('number')!='plur'
        or gap.get('search_incomplete') or d is None
        or d.selector_outcome not in {'INSUFFICIENT_CONTEXT','MULTIPLE_ADMISSIBLE','NONE_FIT'}):return None
    anonymous=next((o for o in gap['options'] if o['kind']=='ANONYMOUS'),None)
    if anonymous is None:return None
    # The identity Decision and all its alternatives remain unresolved.
    key=gap['gap_id']+'|group_existence'
    exist=Decision('implicit_group_existence',key,(anonymous['candidate_id'],))
    exist.selected,exist.outcome,exist.lifecycle=(anonymous['candidate_id'],),'RESOLVED','PROVISIONAL'
    exist.grounds.append(Ground('D','plural subject agreement licenses an unidentified group; no membership/inequality inferred',anonymous['candidate_id']))
    state.decisions[key]=exist
    state.syntax_trace.append({'kind':'UNRESOLVED_GROUP_IDENTITY','decision_ref':gap['gap_id'],'existence_decision_ref':key})
    return {'entity_ref':anonymous['entity_ref'],'participant_kind':'GROUP','anonymous':True,
            'features':gap['features'],'decision_ref':key}
