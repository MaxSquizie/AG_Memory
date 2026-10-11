"""Bounded postnominal area proposals from morphology and released connectors."""
from .component_policy import compatible, _features
from .canonical_ledger import digest
from .component_probe import _probe


def agreeing(host, participle):
    return (host.pos in {'NOUN', 'NPRO'} and bool(host.cases & participle.cases)
            and compatible(_features(host), _features(participle)))


def starts(tokens, rules):
    for index, token in enumerate(tokens):
        matches = []
        for rule in rules['relative_markers']:
            if any(v.lemma == rule['lemma'] and v.pos == rule['POS'] for v in token.variants):
                matches.append({'kind': 'RELATIVE', 'rule': rule})
        for variant in token.variants:
            if variant.pos == 'PRTF' and any(
                    agreeing(v, variant) for h in tokens[:index] for v in h.variants):
                matches.append({'kind': 'PARTICIPLE'})
        if matches and any(v.pos in {'NOUN', 'NPRO'} for h in tokens[:index] for v in h.variants):
            unique = {digest(m): m for m in matches}
            yield index, list(unique.values())


def select(state, release, selector, region, tokens, cfg):
    entries = list(starts(tokens, cfg['refinement']))
    if not entries:
        return None
    index, kinds = entries[0]
    options = {}
    for spec in kinds:
        # Commas add endpoints, but absence of a comma never removes the
        # morphology-based endpoint before a possible resumed finite clause.
        ends = {len(tokens)} | {i for i in range(index+1, len(tokens))
            if tokens[i].span == ',' or any(v.pos == 'VERB' for v in tokens[i].variants)}
        for end in sorted(ends):
            body = tokens[index:end]
            if spec['kind'] == 'RELATIVE' and not any(v.pos == 'VERB' for t in body[1:] for v in t.variants):
                continue
            if spec['kind'] == 'PARTICIPLE' and len(body) < 1:
                continue
            cid = digest([region.region_id, index, end, spec])
            options[cid] = {**spec, 'start': index, 'end': end}
    if not options or len(options) > cfg['max_candidates']:
        state.diag('COMPONENT_REFINEMENT_SEARCH_INCOMPLETE', region.region_id)
        return False
    raw = state.text[slice(*region.source_range)]
    if len(raw) > cfg['context_chars']:
        state.diag('COMPONENT_REFINEMENT_SEARCH_INCOMPLETE', region.region_id)
        return False
    choices = [{'candidate_id': cid, 'label': spec['kind']+' description = «'+
        state.text[tokens[index].start:tokens[spec['end']-1].end]+'»; remaining parent = «'+
        ' '.join(t.span for t in [*tokens[:index], *tokens[spec['end']:]])+'»'}
        for cid, spec in options.items()]
    key = region.region_id+'|refinement-boundary'
    chosen = _probe(state, selector, release, key, 'component_attachment', choices, raw,
        region.source_range, question='Which span is a postnominal description attached to a noun in the remaining parent? '
        'The description may contain further descriptions. Do not use punctuation as proof; '
        'keep all complements belonging to this area. If none of these boundaries is supported, answer ?.')
    state.syntax_trace.append({'kind':'REFINEMENT_BOUNDARY','decision_ref':key,
        'candidates':options,'selected':chosen,'token_refs':[t.token_id for t in tokens]})
    return options[chosen] if chosen else False
