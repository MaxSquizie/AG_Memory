"""Closed probes over code-generated structures; the model cannot add a graph."""
from .canonical_ledger import digest
from .state import Decision, Ground
from .selection_protocol import Relation, DecisionSchema
from .selector_wire import build_selector_prompt, validate_selector_reply


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
        if state.budget.llm_exhausted:
            state.diag('COMPUTATION_LIMIT', row['decision_ref'])
            continue
        relations = {cid: Relation(cid, '; '.join(delta[cid]) or 'No additional attachment',
                                  0, (), 'Existing structural alternative') for cid in ids}
        schema = DecisionSchema(release.sha256, relations)
        prompt = build_selector_prompt(selector, slot_id='structural_attachment', frame_id=row['decision_ref'],
            context_span=state.text[region.source_range[0]:region.source_range[1]], mentions={},
            schema=schema, candidates=ids, contextual_statements=state.context_facts)
        d = Decision('structural_attachment', row['decision_ref'], ids)
        state.decisions[row['decision_ref']] = d
        try:
            state.budget.spend_llm()
            raw = selector.select(prompt)
            reply = validate_selector_reply(selector, raw, schema, ids, allowed=frozenset(ids))
            d.last_prompt, d.raw_response, d.selector_outcome = prompt, raw, reply.outcome
        except Exception as exc:
            d.outcome = 'UNRESOLVED'
            state.diag('REGION_PROBE_FAILED', type(exc).__name__)
            continue
        if reply.outcome != 'ONE_SELECTED':
            d.outcome = 'INSUFFICIENT_CONTEXT' if reply.outcome == 'INSUFFICIENT_CONTEXT' else 'UNRESOLVED'
            continue
        chosen = reply.selected[0]
        d.selected, d.outcome, d.lifecycle = (chosen,), 'RESOLVED', 'PROVISIONAL'
        d.grounds.append(Ground('M', 'bounded attachment choice over released structures', chosen))
        for cid in ids:
            if cid != chosen:
                removed.add(cid)
                state.reject(cid, 'REGION_PROBE', 'M: selected compatible alternative '+chosen)
        state.clarification_candidates.remove(row)
    return [(h, frames) for h, frames in accepted if h.local_id not in removed]
