"""Compatibility adapter for structural deltas, using the common closed probe.

Region-mode runtime resolves source alternatives through CompositionSources.
This entry point remains for older callers; it has no independent selector.
"""
from .canonical_ledger import digest


def _edge_labels(h, evidence):
    def label(index):
        n = h.nodes[index]
        return n.kind + '(' + ' '.join(evidence[a].span+'@'+str(evidence[a].start)
                                     for a in n.anchor_spans) + ')'
    return {f'{label(e.from_idx)} {e.kind}:{e.role_id or ""}:{e.scope or ""} {label(e.to_idx)}'
            for e in h.edges}


def select_generated(state, accepted, selector, release):
    by_id = {h.local_id: (h, frames) for h, frames in accepted}
    evidence = {e.token_id: e for e in state.evidence}
    removed = set()
    for row in list(state.clarification_candidates):
        ids = tuple(o['candidate_id'] for o in row['options'])
        if row['kind'] != 'STRUCTURE' or not set(ids) <= by_id.keys():
            continue
        group = [by_id[cid][0] for cid in ids]
        # Morphological alternatives or different node inventories require a
        # separate typed probe. Never silently equate them by the same labels.
        inventories = [{(n.kind, n.anchor_spans, n.head_anchor, n.feature_refs) for n in h.nodes} for h in group]
        morph = [digest([f.semantic.get('morph_bindings',{}) for f in by_id[cid][1]]) for cid in ids]
        labels = {h.local_id: _edge_labels(h, evidence) for h in group}
        common = set.intersection(*labels.values())
        delta = {cid: sorted(edges-common) for cid, edges in labels.items()}
        anchors = {a for h in group for a in h.alignment}
        start, end = min(evidence[a].start for a in anchors), max(evidence[a].end for a in anchors)
        region = state.region_forest.container(start, end, kinds={'DOCUMENT', 'PARAGRAPH', 'SENTENCE'})
        if (len(ids) > 8 or any(i != inventories[0] for i in inventories) or len(set(morph))!=1
                or len({digest(d) for d in delta.values()}) != len(ids)
                or max(map(len, delta.values())) > 4 or len(region.token_refs) > 256
                or sum(map(len,state.context_facts))>2048):
            state.diag('REGION_PROBE_NOT_LOCAL', row['decision_ref'])
            continue
        from .component_probe import _probe
        choices=[{'candidate_id':cid,'label':'; '.join(delta[cid]) or 'No additional attachment'} for cid in ids]
        chosen=_probe(state,selector,release,row['decision_ref'],'structural_attachment',choices,
            state.text[region.source_range[0]:region.source_range[1]],(start,end),
            question='Which displayed attachment difference fits these occurrences? All alternatives share these fixed links: '+
            ('; '.join(sorted(common)) or 'none')+'. Preserve the common links and compare only the displayed differences.')
        if chosen is None:continue
        for cid in ids:
            if cid != chosen:
                removed.add(cid)
                state.reject(cid, 'REGION_PROBE', 'M: selected compatible alternative '+chosen)
        # The common probe retires the resolved offer.
    return [(h, frames) for h, frames in accepted if h.local_id not in removed]
