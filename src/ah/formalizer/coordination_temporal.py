"""Bounded named-period distribution; shared period is not a shared instant."""
from copy import deepcopy
import re
from .canonical_ledger import digest


def expand(state,release,region,selected,choices,limit):
    raw=state.text[slice(*region.source_range)]
    matches=[(r,m) for r in release.entries('TemporalRules') for m in re.finditer(r['pattern'],raw,re.I)]
    if not matches: return choices
    cfg=release.entries('ProposalPolicy')[0].get('composition',{})
    if (cfg.get('temporal_coordination')!='NAMED_PERIOD_SCOPE_V1' or len(matches)!=1
            or matches[0][0]['kind']!='NAMED_PERIOD' or len(selected)!=2
            or any(c['wrappers'] for c in choices)):
        state.diag('COMPONENT_COORDINATION_TEMPORAL_SCOPE',region.region_id); return []
    rule,match=matches[0];lo=region.source_range[0]+match.start();hi=region.source_range[0]+match.end()
    owners=[i for i,f in enumerate(selected) if f.source_range[0]<=lo<hi<=f.source_range[1]]
    if len(owners)!=1:return []
    from .named_periods import resolve
    temporal,errors=resolve(raw,state.observation,release,source_start=region.source_range[0])
    if temporal is None:return []
    result=[]
    for choice in choices:
        for targets in ([owners[0]],[0,1]):
            item=deepcopy(choice)
            item['candidate_id']='coordination-time:'+digest([choice['candidate_id'],lo,hi,targets])
            item['label']+='; «'+match.group()+'» dates '+('both clauses, independently within that period (not necessarily simultaneous)' if len(targets)==2 else 'only clause '+str(owners[0]+1))
            item['temporal_assignments']={f.frame_id:deepcopy(temporal) if i in targets else None for i,f in enumerate(selected)}
            result.append(item)
    if len(result)>limit:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return []
    return result
