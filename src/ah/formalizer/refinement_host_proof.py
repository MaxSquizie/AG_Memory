"""A selected description owner remains a dependency of parent and children."""
from copy import deepcopy
from .selection_domains import fingerprint
from .selection_evidence import selected_candidate
from .partial_readings import retired_refs


def capture(state,key,selected,premises=()):
    stamp=fingerprint(state,key)
    if stamp is None or selected_candidate(state.decisions.get(key))!=selected:return None
    return {'decision_ref':key,'candidate_id':selected,'fingerprint':stamp,'premises':deepcopy(list(premises)),
            'source_uid':state.source_uid,'interpretation_version':state.interpretation_version}


def live(state,proof):
    if not proof:return False
    key=proof.get('decision_ref')
    result=(proof.get('source_uid')==state.source_uid
            and proof.get('interpretation_version')==state.interpretation_version
            and key not in retired_refs(state.syntax_trace)
            and proof.get('fingerprint') is not None
            and fingerprint(state,key)==proof['fingerprint']
            and selected_candidate(state.decisions.get(key))==proof.get('candidate_id'))
    if result:
        from .structural_tasks import licensed
        result=all(licensed(state,p) for p in proof.get('premises',()))
    if result:
        from .dispatch_evidence import observe
        observe(state,'REFINEMENT_HOST',proof)
    return result


def frame_live(state,frame):
    sem=frame.semantic
    proofs=sem.get('refinement_owner_proofs',())
    if sem.get('refinement_owner_required') and not proofs:return False
    if not all(live(state,p) for p in proofs):return False
    for arg in sem.get('nominal_args',()):
        if not arg.get('host_selection_required'):continue
        proof=arg.get('host_selection_proof')
        if not live(state,proof) or proof['candidate_id']!=arg.get('host_token_ref'):return False
    return True
