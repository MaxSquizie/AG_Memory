"""Versioned observations; no lexical guessing or access to expected answers."""
from ah.formalizer.canonical_ledger import digest, region, region_data

CONTRACT = 'v7-observer-2'


def open_predicate(source_refs):
    if not source_refs:
        raise ValueError('OPEN_SOURCE_NOT_RECORDED')
    return {'open_source': list(source_refs)}


def discourse(state):
    roots = state.observation.get('discourse_roots', [])
    acts = {row['speech_act'] for row in roots}
    act = next(iter(acts)) if len(acts) == 1 else 'MIXED' if acts else 'UNKNOWN'
    requested=state.observation.get('request_kind')
    if requested in {'QUERY','COMMAND','UNKNOWN'}:act=requested
    return {'modus': 'DECLARATIVE' if act == 'ASSERTION' else act,
            'roots': roots, 'host_request_kind': requested}


def temporal(state, release, assertions):
    """Expose selected sources and verify the normalizer's current input API.

    Expected calendar values remain authored in the independent corpus. This
    observation is a source-licence check, not an independent calendar oracle.
    """
    from ah.formalizer.temporal_functions import normalize
    licenses = []
    allowed = set()
    for frame in state.frames:
        if frame.semantic.get('structural_unresolved'):
            continue
        for unit in frame.semantic.get('temporal_functions', ()):
            value, errors = normalize(state, release, unit)
            licenses.append({'frame_ref': frame.frame_id, 'source_range': unit['source_range'],
                'token_refs': unit['token_refs'], 'proofs': unit['proofs'],
                'region': value, 'errors': errors})
            if value is not None and not errors:
                allowed.add(digest(region_data(region(value))))
    # Explicit typed time slots carry their normalization before seal too.
    for frame in state.frames:
        value=frame.semantic.get('explicit_region')
        if value is not None and not frame.semantic.get('structural_unresolved'):
            allowed.add(digest(region_data(region(value))))
    invented = [a for a in assertions
        if a['provenance']['source'].get('source_tag') == [state.source_uid, state.interpretation_version]
        and digest(region_data(region(a['region']))) not in allowed]
    return {'invented_past_intervals': invented, 'clock_default_used': False,
            'licenses': licenses}
