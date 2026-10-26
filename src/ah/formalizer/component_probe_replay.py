"""Preserve unchanged pre-seal probe evidence during declared component repair."""
from copy import deepcopy
from dataclasses import asdict
from .canonical_ledger import digest
from .state import Decision,Ground,ResourceProvenance
from .selection_evidence import selected_candidate


def execute(live,state,selector,release,key,slot,options,context,source_range,*,equivalent_targets=None,question=None,dependency_signature=None,offer_clarification=True):
    signature=digest([release.sha256,slot,options,context,source_range,equivalent_targets,question])
    frozen=state.observation.get('clarification_generation') or {}
    current=state.component_probe_records.get(key)
    prior=current or (frozen.get('component_probe_records',{}).get(key) if frozen.get('rebuild_components') else None)
    explicit=key in state.observation.get('clarification_choices',{})
    reusable=prior is not None and prior['signature']==signature and prior.get('dependency_signature')==dependency_signature and not prior.get('superseded_by')
    if reusable and not explicit:
        signature=prior['signature']
        d=restore_decision(state,key,prior['decision'])
        state.syntax_trace.append({'kind':'COMPONENT_PROBE_REUSED','decision_ref':key,'signature':signature})
        result=selected_candidate(d)
    else:
        result=live(state,selector,release,key,slot,options,context,source_range,
                    equivalent_targets=equivalent_targets,question=question,offer_clarification=offer_clarification)
    attempts=deepcopy(prior.get('attempts',[])) if prior else []
    if prior and (prior['signature']!=signature or prior.get('dependency_signature')!=dependency_signature):
        attempts.append({k:deepcopy(v) for k,v in prior.items() if k!='attempts'})
        state.decisions[key].history.append({'kind':'PARENT_CONSTRAINT_RECHECK',
            'previous_signature':prior['signature'],'previous_outcome':prior['decision']['outcome']})
    if result is not None:
        state.clarification_candidates[:]=[r for r in state.clarification_candidates if r['decision_ref']!=key]
    state.component_probe_records[key]={'signature':signature,'dependency_signature':dependency_signature,
                                      'decision':asdict(state.decisions[key]),'attempts':attempts}
    return result


def supersede(state,previous,current):
    """Retire a replaced question, retaining its exact reply as audit evidence."""
    if not previous or previous==current:return
    state.clarification_candidates[:]=[r for r in state.clarification_candidates if r['decision_ref']!=previous]
    record=state.component_probe_records.get(previous)
    if record is not None:record['superseded_by']=current
    state.syntax_trace.append({'kind':'COMPOSITION_PROBE_SUPERSEDED',
                               'previous_decision_ref':previous,'decision_ref':current})


def restore_decision(state,key,record):
    """Rehydrate probe evidence without inheriting a consumer's validation."""
    raw=deepcopy(record)
    raw['candidates']=tuple(raw['candidates']);raw['selected']=tuple(raw['selected'])
    raw['grounds']=[Ground(**g) for g in raw['grounds']]
    provenance=raw['provenance'];provenance['pattern_ids']=tuple(provenance['pattern_ids'])
    raw['provenance']=ResourceProvenance(**provenance)
    if raw.get('outcome')=='RESOLVED':raw['outcome']=None
    raw['history']=[h for h in raw['history'] if not isinstance(h,dict) or h.get('kind')!='SEMANTIC_VALIDATION']
    raw['search_complete']=False
    raw['machine_state']='OPEN'
    raw['lifecycle']='PROVISIONAL' if raw['selected'] else 'OPEN'
    decision=Decision(**raw);state.decisions[key]=decision
    return decision
