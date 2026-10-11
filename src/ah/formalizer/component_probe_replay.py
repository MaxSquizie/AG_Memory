"""Preserve unchanged pre-seal probe evidence during declared component repair."""
from copy import deepcopy
from dataclasses import asdict
from .canonical_ledger import digest
from .state import Decision,Ground,ResourceProvenance


def execute(live,state,selector,release,key,slot,options,context,source_range,*,equivalent_targets=None,question=None):
    signature=digest([release.sha256,slot,options,context,source_range,equivalent_targets,question])
    frozen=state.observation.get('clarification_generation') or {}
    prior=frozen.get('component_probe_records',{}).get(key) if frozen.get('rebuild_components') else None
    explicit=key in state.observation.get('clarification_choices',{})
    if prior is not None and prior['signature']==signature and not explicit:
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
    state.component_probe_records[key]={'signature':signature,'decision':asdict(state.decisions[key])}
    return result
