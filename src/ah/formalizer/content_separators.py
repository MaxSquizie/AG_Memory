"""Propose CONTENT punctuation ownership without deleting lexical material.

Only a closed delimiter pair containing the selected body alone can leave the
parent. Nested or unfinished scopes remain owned by their original area. The
result is still a proposal, confirmed by the ordinary whole-partition probe.
"""
from .regions import delimiter_scopes


def separate(state,region,tokens,parent,body):
    body_ids={t.token_id for t in body}
    detached=set()
    for scope in delimiter_scopes(state.text):
        if not scope['closed']:continue
        a,b=scope['source_range']
        interior=[t for t in tokens if a<t.start and t.end<b]
        # A body may omit a final period, but not another proposition, a
        # question marker, or an inner delimiter still requiring composition.
        if (not body_ids or not body_ids<={t.token_id for t in interior} or
                any(t.token_id not in body_ids and t.span!='.' for t in interior)):
            continue
        detached.update(t.token_id for t in parent if (t.start==a or t.end==b))
    proposed=[t for t in parent if t.token_id not in detached]
    # Clause separators at an edge are proposed as relation punctuation.
    # A clock colon, inner comma, question mark and unclosed quote stay put.
    while proposed and proposed[0].span in {',',':','.'}:
        detached.add(proposed.pop(0).token_id)
    while proposed and proposed[-1].span in {',',':','.'}:
        detached.add(proposed.pop().token_id)
    trace=None
    if detached:
        trace={'kind':'CONTENT_SEPARATOR_OWNERSHIP','region_ref':region.region_id,
            'source_range':list(region.source_range),'parent_before':[t.token_id for t in parent],
            'parent_after':[t.token_id for t in proposed],'content_refs':[t.token_id for t in body],
            'separator_refs':[t.token_id for t in tokens if t.token_id in detached],
            'status':'PROPOSED'}
        state.syntax_trace.append(trace)
    return proposed,trace
