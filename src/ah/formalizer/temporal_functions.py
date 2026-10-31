"""T2 selects temporal use; calendar parsers only normalize that selected use.

The domain is source occurrences, independent of spelling and morphology. A
normalizer missing a selected expression is an implementation gap, never proof
that the expression was not temporal. No guessed timestamp is emitted.
"""
from .canonical_ledger import digest
from .task_contracts import SelectionPurpose
from .structural_tasks import choose, source_set


def prepare(state, release, selector, region, tokens, cfg):
    from .function_inventory import begin,complete
    inventory=begin(state,'TEMPORAL',tokens,cfg.get('_task_constraints'))
    if inventory is None:return True
    remaining = list(tokens)
    while remaining:
        result = choose(state, release, selector, region, cfg, 'temporal_function', [
            *[{'candidate_id':'time:'+t.token_id,'index':i,'token_ref':t.token_id,
               'label':'A time expression starts at «'+t.span+'» @'+str(t.start)}
              for i,t in enumerate(remaining)]],
            'Find separate words that answer WHEN, FOR HOW LONG or HOW OFTEN the target event/state holds. '
            'Select the first word of the FIRST such expression. Verb tense alone is not a separate time expression. '
            'If the target only names participants and an action, with no time wording, answer 0. '
            'The actual date need not be known to recognize relative time wording. '
            'Use ? only if you cannot decide the function of words actually present; missing event date is not a reason for ?. '
            'A word mentioned as a name/title is not a time use. '
            'Target words: «' +
            ' '.join(t.span for t in remaining) + '».',
            empty={'candidate_id':'NONE','label':'no remaining time expression'},purpose=SelectionPurpose.NEXT)
        if not result:
            return False
        if result[0]['candidate_id'] == 'NONE':
            return complete(state,inventory,result[1])
        selected = source_set(state, release, selector, region, remaining, cfg, 'temporal_source',
                              'Select one whole temporal expression, including its qualifiers.',initial=result)
        if not selected:
            return False
        owned, proofs = selected
        refs = [t.token_id for t in owned]
        key = 'time-use:' + digest([region.region_id, refs])
        state.syntax_trace.append({**inventory,'kind': 'TEMPORAL_FUNCTION', 'unit_ref': key,
            'region_ref': region.region_id, 'source_range': [owned[0].start, owned[-1].end],
            'token_refs': refs, 'proofs': proofs})
        remaining = [t for t in remaining if t.token_id not in refs]
    return complete(state,inventory)


def units(state, token_refs=None):
    from .function_inventory import unit_live
    allowed = set(token_refs) if token_refs is not None else None
    found = {}
    for row in state.syntax_trace:
        if row.get('kind') == 'TEMPORAL_FUNCTION' and not row.get('superseded') and (allowed is None or set(row['token_refs']) <= allowed) and unit_live(state,row,scoped=True):
            found[tuple(row['token_refs'])] = row
    return list(found.values())


def owned_refs(state, tokens=None):
    return {tid for row in units(state, [t.token_id for t in tokens] if tokens is not None else None)
            for tid in row['token_refs']}


def normalize(state, release, row):
    from .function_inventory import unit_live
    if not unit_live(state,row,scoped=True):return None,['FUNCTION_INVENTORY_UNRESOLVED']
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
