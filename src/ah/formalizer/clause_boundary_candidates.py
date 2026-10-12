"""Morphological boundary proposals; a proposal never establishes scope."""
from .component_policy import compatible, _features
from .component_phrases import prepositional_groups


def finite(token):
    return [v for v in token.variants if v.pos == 'VERB' and v.mood != 'imperative']


def subject_starts(state, release, region, tokens, cfg):
    """Separate finite heads with a possible explicit subject of the latter.

    Works without punctuation/capitalization. Relative markers, conjunctions
    and governed nominals stay with their existing composition mechanisms.
    Whole readings must agree; no nearest-name identity or lexical rule.
    """
    from .component_area_scope import connectives
    connectors = connectives(state, release, region, tokens)
    governed = {ref for g in prepositional_groups(tokens).values() for ref in g['anchor_refs']}
    markers = cfg.get('refinement', {}).get('relative_markers', ())
    heads = [i for i, token in enumerate(tokens) if finite(token)]
    result = set()
    for left, right in zip(heads, heads[1:]):
        between = tokens[left+1:right]
        if any(tokens[left].end <= a < tokens[right].start for a, _ in connectors):
            continue
        if any(v.lemma == r['lemma'] and v.pos == r['POS']
               for token in between for v in token.variants for r in markers):
            continue
        for i in range(left+1, right):
            token = tokens[i]
            readings = [v for v in token.variants if v.pos in {'NOUN', 'NPRO'}
                        and 'nom' in v.cases and any(compatible(_features(v), _features(p))
                                                   for p in finite(tokens[right]))]
            if token.token_id in governed or not readings:
                continue
            start = i
            while start > left+1 and any(v.pos == 'ADJF' and 'nom' in v.cases
                    and compatible(_features(v), _features(n))
                    for v in tokens[start-1].variants for n in readings):
                start -= 1
            result.add(start)
    return result
