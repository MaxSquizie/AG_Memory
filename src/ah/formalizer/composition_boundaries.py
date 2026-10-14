"""Choose one outer source edge; its children re-enter the same composer.

This is topology selection, not a second clause/operator parser. Candidate
boundaries are released connectives with predicative evidence on both sides.
An internal-marker alternative preserves nominal and wider unary readings.
"""
from bisect import bisect_left, bisect_right
from .component_area_scope import connectives
from .component_probe import _probe
from .canonical_ledger import digest


def select(state, release, selector, region, tokens, cfg):
    if 'AND' not in cfg.get('coordination_operators', ()):
        return None
    spans = connectives(state, release, region, tokens)
    if not spans:
        return None
    heads = sorted((t.start, t.end) for t in tokens if any(
        (v.pos == 'VERB' and v.mood != 'imperative') or v.pos == 'INFN'
        or v.pos in cfg.get('quality_predicate_pos', ()) for v in t.variants))
    starts, ends = [a for a, b in heads], [b for a, b in heads]
    candidates = [(a, b) for a, b in spans
                  if bisect_right(ends, a) and bisect_left(starts, b) < len(heads)]
    if not candidates:
        return None
    from .operator_composition import lexical_matches
    unary = lexical_matches(state,release,region,tokens)
    from .quantifier_composition import lexical_matches as quantified_matches
    quantified=quantified_matches(state,release,region,tokens)
    if quantified is None:return False
    unary={**unary,**quantified}
    if (len(candidates) + len(unary) + 1 > cfg['max_candidates']
            or region.source_range[1]-region.source_range[0]>cfg['context_chars']):
        state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
        return False
    lo, hi = region.source_range
    options = [{'candidate_id': 'boundary:' + digest([region.source_range, a, b]),
                'label': 'Outer AND: «' + state.text[lo:a].strip() + '» | «' +
                         state.text[b:hi].strip() + '»; each child keeps its own operators and agreement'}
               for a, b in candidates]
    choices={option['candidate_id']:{'kind':'CONNECTIVE','span':bounds}
             for option,bounds in zip(options,candidates)}
    for a,b,operator in sorted(unary):
        cid='outer-operator:'+digest([a,b,operator])
        options.append({'candidate_id':cid,'label':'Outer '+operator+' «'+state.text[a:b]+
                        '» at '+str([a,b])+': its content is the whole remaining area, including the conjunction'})
        choices[cid]={'kind':'UNARY','operator':(a,b,operator)}
    options.append({'candidate_id': 'INTERNAL', 'label':
        'Defer root selection: resolve a nominal/relative/other child first; no listed outer edge is established or excluded yet'})
    key = region.region_id + '|outer-boundary:' + digest([options, [t.token_id for t in tokens]])
    chosen = _probe(state, selector, release, key, 'composition_boundary', options,
        state.text[lo:hi], region.source_range,
        question='Select the outer connection of this source area before parsing its children. '
        'Do not move an operator across the selected boundary. If one operator governs the whole '
        'coordination, select that outer operator; its content slot must remain the whole area. '
        'For a plain associative chain of actions choose the leftmost outer connector; '
        'this is structural bracketing, not temporal order. Grammar and context override this preference.')
    state.syntax_trace.append({'kind': 'COMPOSITION_BOUNDARY', 'region_ref': region.region_id,
        'decision_ref': key, 'alternatives': options, 'selected': chosen})
    if chosen == 'INTERNAL':
        return None
    return choices.get(chosen,False)
