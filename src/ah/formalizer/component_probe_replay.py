"""Preserve unchanged pre-seal probe evidence during declared component repair."""
from copy import deepcopy
from dataclasses import asdict
from .canonical_ledger import digest
from .state import Decision,Ground,ResourceProvenance


def execute(live,state,selector,release,key,slot,options,context,source_range,*,equivalent_targets=None,question=None,dependency_signature=None):
    signature=digest([release.sha256,slot,options,context,source_range,equivalent_targets,question])
    frozen=state.observation.get('clarification_generation') or {}
    current=state.component_probe_records.get(key)
    prior=current or (frozen.get('component_probe_records',{}).get(key) if frozen.get('rebuild_components') else None)
    explicit=key in state.observation.get('clarification_choices',{})
    reusable=prior is not None and (prior['signature']==signature or current is not None and
        prior['decision']['outcome']=='RESOLVED' and dependency_signature is not None and
        prior.get('dependency_signature')==dependency_signature)
    if reusable and not explicit:
        signature=prior['signature']
        raw=deepcopy(prior['decision'])
        raw['candidates']=tuple(raw['candidates']);raw['selected']=tuple(raw['selected'])
        raw['grounds']=[Ground(**g) for g in raw['grounds']]
        raw['provenance']=ResourceProvenance(**raw['provenance'])
        d=Decision(**raw);state.decisions[key]=d
        state.syntax_trace.append({'kind':'COMPONENT_PROBE_REUSED','decision_ref':key,'signature':signature})
        result=d.selected[0] if d.outcome=='RESOLVED' and len(d.selected)==1 else None
        if result is None:
            from .clarifications import offer
            offer(state,key,'COMPONENT',context,options)
    else:
        result=live(state,selector,release,key,slot,options,context,source_range,
                    equivalent_targets=equivalent_targets,question=question)
    attempts=deepcopy(prior.get('attempts',[])) if prior else []
    if prior and prior['signature']!=signature:
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
