"""Exhaust a produced domain before licensing a unique nominal identity.

Each page assesses all compatible alternatives in its own list. A page success
is never the union result; unknown/failed pages cannot be treated as empty.
"""
from dataclasses import asdict
from .canonical_ledger import digest
from .state import Decision, Ground
from .selection_evidence import selected_candidate


def proof(state, key):
    record=state.component_probe_records.get(key)
    d=state.decisions.get(key)
    if not record or record.get('superseded_by') or not d:return None
    evidence=asdict(d)
    # Dispatcher promotion is bookkeeping, not a changed model judgment.
    for field in ('machine_state','lifecycle','search_complete'):evidence.pop(field,None)
    if evidence['outcome']=='RESOLVED':evidence['outcome']=None
    evidence['history']=[h for h in evidence['history'] if h.get('kind')!='SEMANTIC_VALIDATION']
    return {'decision_ref':key,'record_hash':digest(record),'decision_hash':digest(evidence),
            'selected':list(d.selected),'selector_outcome':d.selector_outcome,
            'supported':selected_candidate(d)}


def live(state, proofs):
    return bool(proofs) and all(proof(state,p['decision_ref'])==p for p in proofs)


def select(state,release,selector,key,options,context,source_range,targets,inputs,question):
    from .component_probe import _probe
    from .clarifications import choice
    state.clarification_candidates[:]=[r for r in state.clarification_candidates if r['decision_ref']!=key]
    ids=tuple(o['candidate_id'] for o in options)
    aggregate=Decision('reference',key,ids,search_complete=False)
    state.decisions[key]=aggregate
    explicit=choice(state,key,ids)
    if explicit is not None:
        aggregate.selected=(explicit,);aggregate.lifecycle='PROVISIONAL'
        aggregate.grounds.append(Ground('C','explicit nominal identity clarification',explicit))
        return explicit,[],False
    labels={}
    for o in options:labels.setdefault(o['label'],set()).add(targets[o['candidate_id']])
    if any(len(v)>1 for v in labels.values()):
        aggregate.outcome='UNRESOLVED'
        state.diag('PROBE_OPTIONS_INDISTINGUISHABLE',key)
        return None,[],True
    pending=[options[i:i+32] for i in range(0,len(options),32)]
    accepted=[];proofs=[];unknown=False
    while pending:
        page=pending.pop(0)
        page_key=key+'|page:'+digest(page)
        before=len(state.diagnostics)
        picked=_probe(state,selector,release,page_key,'reference',page,context,source_range,
            inputs=inputs(page),equivalent_targets={o['candidate_id']:targets[o['candidate_id']] for o in page},
            question=question+' This is one page of a larger candidate domain. Assess every option on this page against the supplied source. List all admissible alternatives on this page; do not prefer one merely because other candidates are on another page. 0 rejects only this page.')
        d=state.decisions[page_key]
        # Split only an oversized prompt, never a valid ?, 0, or model answer.
        oversized=any(h.get('kind')=='PROBE_LIMIT' and str(h.get('detail','')).startswith('COMPUTATION_LIMIT: prompt_chars:') for h in d.history)
        if oversized and len(page)>1:
            # The rejected oversized request spent no model call. Its exact
            # failure remains in the page record, but is not a terminal limit.
            del state.diagnostics[before:]
            cut=len(page)//2;pending[0:0]=[page[:cut],page[cut:]]
            aggregate.history.append({'kind':'REFERENCE_PAGE_SPLIT','decision_ref':page_key,'candidate_count':len(page)})
            continue
        p=proof(state,page_key)
        if p:proofs.append(p)
        if picked is not None:accepted.append(picked)
        elif d.selector_outcome=='MULTIPLE_ADMISSIBLE':accepted.extend(d.selected)
        elif d.selector_outcome!='NONE_FIT':unknown=True
        if not p:unknown=True
    accepted=list(dict.fromkeys(accepted))
    aggregate.history.append({'kind':'NOMINAL_REFERENCE_DOMAIN_PAGES','pages':proofs,
        'enumerated_candidates':list(ids),'admissible':accepted,'evaluation_complete':not unknown,
        'scope':'PRODUCED_REFERENCE_UNION_ONLY'})
    aggregate.selected=tuple(accepted)
    # This is enumeration/evaluation completeness, not complete interpretation.
    aggregate.search_complete=False
    if unknown:
        aggregate.outcome='INSUFFICIENT_CONTEXT';return None,proofs,True
    if accepted and len({targets[c] for c in accepted})==1:
        chosen=min(accepted);aggregate.selected=(chosen,);aggregate.lifecycle='PROVISIONAL'
        aggregate.grounds.append(Ground('D','All evaluated pages support one established target; page model evidence retained',chosen))
        return chosen,proofs,False
    aggregate.outcome='AMBIGUOUS' if accepted else 'NO_CANDIDATE'
    return None,proofs,False
