"""Evidence for exhausting exactly one caller-supplied candidate enumeration.

Both accepted and rejected pages are dependencies. This does not certify that
an iterator covers all linguistic interpretations or that a model is correct.
"""
from .canonical_ledger import digest
from .selection_evidence import selected_candidate


def fingerprint(state,key):
    decision=state.decisions.get(key)
    record=state.component_probe_records.get(key)
    if decision is None or record is None or record.get('superseded_by'):return None
    return digest([decision.slot_id,decision.candidates,decision.selected,
        decision.selector_outcome,decision.outcome,
        [(g['type'],g['text'],g.get('value')) if isinstance(g,dict)
         else (g.type,g.text,g.value) for g in decision.grounds],
        record.get('signature'),record.get('dependency_signature')])


def capture(state,key,values):
    decision=state.decisions.get(key)
    selected=selected_candidate(decision)
    outcome='ONE_SELECTED' if selected is not None else getattr(decision,'selector_outcome',None)
    if outcome not in {'ONE_SELECTED','MULTIPLE_ADMISSIBLE','NONE_FIT'}:return None
    supported=[selected] if selected is not None else list(decision.selected)
    ids=[v['candidate_id'] for v in values]
    if (len(set(ids))!=len(ids) or not set(supported)<=set(ids)
            or (outcome=='ONE_SELECTED' and len(supported)!=1)
            or (outcome=='NONE_FIT' and supported)
            or (outcome=='MULTIPLE_ADMISSIBLE' and len(supported)<2)):return None
    stamp=fingerprint(state,key)
    if stamp is None:return None
    return {'decision_ref':key,'fingerprint':stamp,'candidate_ids':ids,
        'candidate_payloads':{v['candidate_id']:digest(v) for v in values},
        'supported_ids':supported,'outcome':outcome}


def valid(state,record,retired=None):
    if retired is None:
        from .partial_readings import retired_refs
        retired=retired_refs(state.syntax_trace)
    from .task_contracts import SelectionPurpose
    if record.get('selection_purpose') not in {p.value for p in SelectionPurpose}:return False
    evidence=record.get('page_evidence')
    if evidence is None or record.get('multiplicity')!='ALTERNATIVE_READINGS':return False
    refs=[p['decision_ref'] for p in evidence]
    if refs!=record.get('page_refs') or len(set(refs))!=len(refs) or retired.intersection(refs):return False
    if record.get('enumeration_complete') is not True or record.get('enumeration_scope')!='CALLER_GENERATOR':return False
    candidates=[];supported=[];payloads={}
    for page in evidence:
        stamp=fingerprint(state,page['decision_ref'])
        if stamp is None or page.get('fingerprint')!=stamp:return False
        ids=page.get('candidate_ids',());picks=page.get('supported_ids',())
        if not set(picks)<=set(ids):return False
        if page.get('outcome') not in {'ONE_SELECTED','MULTIPLE_ADMISSIBLE','NONE_FIT'}:return False
        if ((page['outcome']=='NONE_FIT' and picks) or
                (page['outcome']=='ONE_SELECTED' and len(picks)!=1) or
                (page['outcome']=='MULTIPLE_ADMISSIBLE' and len(picks)<2)):return False
        candidates.extend(ids);supported.extend(picks)
        payloads.update({cid:page['candidate_payloads'].get(cid) for cid in picks})
    return (len(set(candidates))==len(candidates)
        and sorted(candidates)==record.get('candidate_ids')
        and sorted(supported)==record.get('supported_ids')
        and payloads==record.get('supported_payloads'))


def valid_frozen(snapshot,record):
    """Check the same evidence in a serialized clarification generation."""
    from types import SimpleNamespace
    probes=snapshot.get('component_probe_records',{})
    decisions={}
    for ref in record.get('page_refs',()):
        raw=probes.get(ref,{}).get('decision')
        if raw is None:return False
        decisions[ref]=SimpleNamespace(**{**raw,
            'grounds':[SimpleNamespace(**g) for g in raw['grounds']]})
    return valid(SimpleNamespace(decisions=decisions,component_probe_records=probes,
        syntax_trace=snapshot.get('syntax_trace',())),record)
