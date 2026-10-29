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
    selected=[];evidence={t.token_id:t for t in state.evidence}
    for frame in pending:
        for row in frame.semantic['relative_temporal']:
            anchor=evidence.get(row.get('anchor_ref'))
            if anchor is None:
                state.diag('PROBE_INPUT_INCOMPLETE',frame.frame_id+': TEMPORAL_ANCHOR_UNAVAILABLE');return False
            from .probe_wording import frame_label
            label=(row['operator']+'(event '+frame_label(state,frame)+', anchor «'+anchor.span+
                   '» @'+str(anchor.start)+':'+str(anchor.end)+')')
            key=region.region_id+'|relative-scope:'+digest([root.frame_id,frame.frame_id,row])
            choice=_probe(state,selector,release,key,'temporal_scope',[
                {'candidate_id':'SOURCE_ASSERTED','label':label+' is directly asserted by the source; other modifiers preserve this temporal relation'},
                {'candidate_id':'EMBEDDED','label':label+' is only embedded under modality, negation, report, or another unasserted scope'}],
                raw,region.source_range,question='Resolve the scope of this ONE written temporal relation. '
                'Do not infer occurrence, calendar dates or world truth. Select SOURCE_ASSERTED only if the wording itself asserts this ordering for the named event. '
                'Select EMBEDDED for an explicitly non-asserted scope; answer ? if the wording is insufficient.',
                target_refs=tuple(dict.fromkeys((frame.predicate_token_ref,anchor.token_id))))
            state.syntax_trace.append({'kind':'RELATIVE_EVENT_SCOPE','decision_ref':key,
                'root_ref':root.frame_id,'target_ref':frame.frame_id,'rows':[deepcopy(row)],'selected':choice})
            if choice!='SOURCE_ASSERTED':
                state.diag('TEMPORAL_NESTED_SCOPE_UNSUPPORTED' if choice=='EMBEDDED' else 'COMPONENT_TEMPORAL_SCOPE_UNRESOLVED',region.region_id)
                return False
            selected.append({'frame_ref':frame.frame_id,'rows':[deepcopy(row)],'decision_ref':key})
    # Commit the transfer only after every independently addressed relation closes.
    root.semantic['relative_time_targets']=selected
    for frame in pending:frame.semantic['relative_temporal']=[]
    return True
