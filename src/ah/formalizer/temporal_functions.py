"""T2 selects temporal use; calendar parsers only normalize that selected use.

The domain is source occurrences, independent of spelling and morphology. A
normalizer missing a selected expression is an implementation gap, never proof
that the expression was not temporal. No guessed timestamp is emitted.
"""
from .canonical_ledger import digest
from .structural_tasks import choose, source_set


def prepare(state, release, selector, region, tokens, cfg):
    from .function_inventory import begin,complete
    inventory=begin(state,'TEMPORAL',tokens,cfg.get('_task_constraints'))
    if inventory is None:return True
    remaining = list(tokens)
    while remaining:
        result = choose(state, release, selector, region, cfg, 'temporal_function', [
            {'candidate_id': 'NONE', 'label': 'No remaining words specify calendar time, duration or clock time'},
            {'candidate_id': 'TIME', 'label': 'Remaining words specify calendar time, duration or clock time'}],
            'Classify the function in this clause, not the spelling. A name, title, quantity or quoted word is not time. '
            'Event-to-event relations have already been handled. Remaining words: «' +
            ' '.join(t.span for t in remaining) + '».')
        if not result:
            return False
        if result[0]['candidate_id'] == 'NONE':
            complete(state,inventory)
            return True
        selected = source_set(state, release, selector, region, remaining, cfg, 'temporal_source',
                              'Select one whole temporal expression, including its qualifiers.')
        if not selected:
            return False
        owned, proofs = selected
        refs = [t.token_id for t in owned]
        key = 'time-use:' + digest([region.region_id, refs])
        state.syntax_trace.append({**inventory,'kind': 'TEMPORAL_FUNCTION', 'unit_ref': key,
            'region_ref': region.region_id, 'source_range': [owned[0].start, owned[-1].end],
            'token_refs': refs, 'proofs': [result[1], *proofs]})
        remaining = [t for t in remaining if t.token_id not in refs]
    complete(state,inventory)
    return True


def units(state, token_refs=None):
    allowed = set(token_refs) if token_refs is not None else None
    found = {}
    for row in state.syntax_trace:
        if row.get('kind') == 'TEMPORAL_FUNCTION' and not row.get('superseded') and (allowed is None or set(row['token_refs']) <= allowed):
            found[tuple(row['token_refs'])] = row
    return list(found.values())


def owned_refs(state, tokens=None):
    return {tid for row in units(state, [t.token_id for t in tokens] if tokens is not None else None)
            for tid in row['token_refs']}


def normalize(state, release, row):
    from .native_frontend import _temporal
    refs = set(row['token_refs'])
    lo, hi = row['source_range']
    chars = list(state.text[lo:hi])
    for token in state.evidence:
        if token.token_id not in refs and lo <= token.start < hi:
            chars[token.start-lo:token.end-lo] = ' ' * (token.end-token.start)
    value, errors = _temporal(''.join(chars), state.observation, release, source_start=lo)
    if value is None and not errors:
        errors = ['TEMPORAL_NORMALIZATION_UNSUPPORTED']
    return value, errors
