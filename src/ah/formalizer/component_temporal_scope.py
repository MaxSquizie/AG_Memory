"""Keep time on its event while completing other dependencies around that event."""
from copy import deepcopy
from .component_probe import _probe
from .component_source import view
from .canonical_ledger import digest


def resolve(state,release,selector,region,tokens,bundle,cfg):
    root=bundle[-1]
    pending=[f for f in bundle if f is not root and f.semantic.get('relative_temporal')]
    if not pending:return True
    raw=view(state,region,tokens)
    if len(raw)>cfg['context_chars']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return False
    selected=[]
    for frame in pending:
        rows=frame.semantic['relative_temporal']
        label='; '.join(r['operator']+'(event «'+frame.anchor_span+'», anchor «'+r['anchor_surface']+'»)' for r in rows)
        key=region.region_id+'|relative-scope:'+digest([root.frame_id,frame.frame_id,rows])
        choice=_probe(state,selector,release,key,'temporal_scope',[
            {'candidate_id':'SOURCE_ASSERTED','label':label+' is directly asserted by the source; other modifiers preserve this temporal relation'},
            {'candidate_id':'EMBEDDED','label':'The temporal relation is only embedded under modality, negation, report, or another unasserted scope'}],
            raw,region.source_range,question='Resolve the scope of the written temporal phrase. '
            'Do not infer occurrence, calendar dates or world truth. Select SOURCE_ASSERTED only if the wording itself asserts this ordering for the named event. '
            'Select EMBEDDED for an explicitly non-asserted scope; answer ? if the wording is insufficient.')
        state.syntax_trace.append({'kind':'RELATIVE_EVENT_SCOPE','decision_ref':key,
            'root_ref':root.frame_id,'target_ref':frame.frame_id,'rows':deepcopy(rows),'selected':choice})
        if choice!='SOURCE_ASSERTED':
            state.diag('TEMPORAL_NESTED_SCOPE_UNSUPPORTED' if choice=='EMBEDDED' else 'COMPONENT_TEMPORAL_SCOPE_UNRESOLVED',region.region_id)
            return False
        selected.append({'frame_ref':frame.frame_id,'rows':deepcopy(rows),'decision_ref':key})
    # Only after every required scope is resolved: no half-transfer of a bundle.
    root.semantic['relative_time_targets']=selected
    for frame in pending:frame.semantic['relative_temporal']=[]
    return True
