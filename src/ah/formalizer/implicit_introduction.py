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
