"""Readable linguistic graph choices for the optional legacy TP selector."""
from .probe_wording import role


def describe(state,hypothesis):
    evidence={e.token_id:e for e in state.evidence}
    hypotheses={h.hypothesis_id:h for h in getattr(state,'token_hypotheses',())}
    def surface(ref):
        e=evidence[ref];return '«'+e.span+'» @'+str(e.start)
    rows=[]
    for i,node in enumerate(hypothesis.nodes,1):
        label='unit '+str(i)+' ('+node.kind.lower().replace('_',' ')+'): '+' '.join(surface(r) for r in node.anchor_spans)
        if node.head_anchor:label+='; head '+surface(node.head_anchor)
        for ref in node.feature_refs:
            feature=hypotheses.get(ref)
            if feature is not None:
                label+='; readings of '+surface(feature.span_ref)+': '+' / '.join(feature.variants)
            else:
                # Keep an explicit unresolved distinction; never invent a form.
                label+='; unavailable reading description'
        rows.append(label)
    for edge in hypothesis.edges:
        rows.append('unit '+str(edge.from_idx+1)+' → unit '+str(edge.to_idx+1)+': '+
                    edge.kind.lower().replace('_',' ')+(('; '+role(edge.role_id)) if edge.role_id else '')+
                    ('; governs its scope' if edge.scope else ''))
    if hypothesis.alignment:rows.append('Source alignment: '+' '.join(surface(r) for r in hypothesis.alignment))
    return '\n'.join(rows)
