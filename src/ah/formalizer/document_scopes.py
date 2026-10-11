"""Source-addressed temporal areas selected before composition, not newline cuts."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_probe import _probe
from .document_calendar import parse, expression
from .regions import build_regions, protected_intervals


def prepare(state, release, selector, frozen=None):
    policy=release.entries('ProposalPolicy')[0].get('document_scopes')
    if not policy or state.observation.get('batch_kind')!='DOCUMENT': return
    if frozen is not None:
        if frozen['resource_snapshot']!=release.sha256: raise ValueError('CLARIFICATION_RESOURCE_STALE')
        state.document_scopes=deepcopy(frozen.get('document_scopes',[]))
        from .state import Decision,Ground,ResourceProvenance
        for row in state.document_scopes:
            key=row['decision_ref']; record=deepcopy(frozen['component_probe_records'][key])
            raw=record['decision'];raw['candidates']=tuple(raw['candidates']);raw['selected']=tuple(raw['selected'])
            raw['grounds']=[Ground(**g) for g in raw['grounds']]
            raw['provenance']=ResourceProvenance(**raw['provenance'])
            state.decisions[key]=Decision(**raw);state.component_probe_records[key]=record
    else:
        protected=protected_intervals(state.text); candidates=[]; offset=0
        for line in state.text.splitlines(keepends=True):
            raw=line.strip(); start=offset+len(line)-len(line.lstrip()); end=start+len(raw)
            if raw and not any(a<end and start<b for a,b in protected):
                matches=[(r,date) for r in policy['rules'] if (date:=parse(raw,r)) is not None]
                if len(matches)>1:
                    state.diag('DOCUMENT_SCOPE_UNRESOLVED',str((start,end))); return
                if matches:
                    rule,date=matches[0]
                    candidates.append({'raw':raw,'source_range':[start,end],
                        'header_range':[offset,offset+len(line)],'calendar':date,'rule_id':rule['rule_id']})
            offset+=len(line)
        accepted=[]
        for i,row in enumerate(candidates):
            end=candidates[i+1]['header_range'][0] if i+1<len(candidates) else len(state.text)
            row['scope_range']=[row['header_range'][0],end]
            row['scope_ref']='region:'+digest([state.source_uid,'TEMPORAL_SCOPE',row['scope_range'],row['calendar']])
            row['decision_ref']=row['scope_ref']+'|document_scope'
            # The following area is addressed, never supplied as a generated fact.
            context=state.text[row['header_range'][0]:min(end,row['header_range'][1]+policy['context_chars'])]
            chosen=_probe(state,selector,release,row['decision_ref'],'document_scope',[
                {'candidate_id':'HEADER','label':'Calendar header dates the following entry, until the next peer calendar header or end of source. Nested temporal expressions retain their own scope.'},
                {'candidate_id':'INLINE','label':'Ordinary text; does not establish a temporal area over the following entry.'}],
                context,tuple(row['source_range']),question='Classify the source line «'+row['raw']+
                '». Layout alone is not evidence of date scope. Do not infer a year, timezone or clock boundaries. Proposed area: '+str(row['scope_range']))
            if chosen!='HEADER':
                # Do not silently extend a prior header across an unresolved peer.
                state.diag('DOCUMENT_SCOPE_UNRESOLVED',row['decision_ref']); return
            accepted.append(row)
        state.document_scopes=accepted
    state.region_forest=build_regions(state.text,state.evidence,state.source_uid,document_scopes=state.document_scopes)
    state.syntax_trace.extend({'kind':'DOCUMENT_TEMPORAL_SCOPE',**row} for row in state.document_scopes)


def inherit(state, frame, region, diagnostics, release):
    owners=[s for s in state.document_scopes if s['header_range'][1]<=frame.source_range[0]
            and frame.source_range[1]<=s['scope_range'][1]]
    if len(owners)!=1: return region,diagnostics
    # A document-global clock anchor cannot override a newly selected header.
    if region and (region.get('point') is not None or region.get('lo') is not None
                   or region.get('hi') is not None or region.get('points')):
        return None,['DOCUMENT_TEMPORAL_ANCHOR_UNRESOLVED']
    # An unresolved explicit expression must not silently become the heading date.
    if region is None and diagnostics: return region,diagnostics
    row=owners[0]; result=deepcopy(region) if region else {'kind':'EXISTENTIAL','lo':None,'hi':None}
    if region is None: frame.semantic['time_scope_owner']=frame.frame_id
    for local in result.get('expressions',[]):
        if local.get('kind')=='NAMED_PERIOD': local['within_scope_ref']=row['scope_ref']
    result.setdefault('expressions',[]).append(expression(row,release.sha256))
    frame.semantic['document_scope_ref']=row['scope_ref']
    return result,diagnostics
