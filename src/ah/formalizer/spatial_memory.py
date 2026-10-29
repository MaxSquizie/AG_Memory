"""Typed place reads from the active workspace, frozen by AttentionContextReader."""
from copy import deepcopy
from .canonical_ledger import digest


def requests(state):
    seen = set()
    for frame in state.frames:
        for slot in frame.semantic.get('spatial_slots', {}).values():
            key = slot['decision_ref']
            if slot['rule']['kind'] != 'REFERENCE' or key in seen:
                continue
            seen.add(key)
            yield {'kind': 'SPATIAL_REFERENCE', 'decision_ref': key,
                   'source_range': slot['target_range'],
                   'cue_token_refs': [slot['mention_ref']]}


def attach(state, request, result, release):
    cfg = release.entries('ProposalPolicy')[0]['spatial_references']
    for frame in state.frames:
        for slot in frame.semantic.get('spatial_slots', {}).values():
            if slot['decision_ref'] != request['decision_ref']:
                continue
            slot['memory_read_hash'] = digest(result)
            by_id = {p['entity_ref']: p for p in slot['options']}
            for row in result['rows']:
                by_id.setdefault(row['entity_ref'], deepcopy(row))
            slot['options'] = list(by_id.values())
            slot['search_incomplete'] |= bool(result.get('search_incomplete')) or len(by_id) > cfg['max_candidates']


def _binding_index(store):
    bindings = store.ledger.data['bindings']
    cached = getattr(store, '_spatial_binding_index', None)
    if cached is None or cached[0] is not bindings or cached[1] != len(bindings):
        index = {}
        for bid, row in bindings.items():
            if row.get('binding_kind') == 'SPATIAL_ANCHOR':
                index.setdefault(row['target_ref'], []).append(bid)
        store._spatial_binding_index = (bindings, len(bindings), index)
    return store._spatial_binding_index[2]


def read_active(store, release, active_refs, source_tags=()):
    """Index lookup only for active M; index membership never establishes liveness."""
    cfg = release.entries('ProposalPolicy')[0].get('spatial_references')
    if not cfg:
        return [], False
    tags = {tuple(t) for t in source_tags}
    paths = store.ledger.paths()
    index = _binding_index(store)
    rows = []
    for uid in sorted(active_refs):
        for bid in index.get(uid, ()):
            b = store.ledger.data['bindings'][bid]
            if not store.ledger.binding_live(bid, paths):
                continue
            if tags and tuple(b['source_tag']) not in tags:
                continue
            entity = store._store.get_element_any_domain(uid)
            place = entity.meta.get('relative_place')
            if not place or place['source_tag'] != b['source_tag']:
                continue
            rows.append({**deepcopy(place), 'entity_ref': uid, 'memory_binding_ref': bid})
            if len(rows) > cfg['max_candidates']:
                return [], True  # No silent top-k presented as complete evidence.
    wanted = {tuple(r['source_tag']) for r in rows}
    texts = {}
    if wanted:
        for rec in store._journal.scan_unprocessed():
            p = rec['payload']
            tag = (p.get('observation_id'), p.get('version'))
            if p.get('kind') == 'run_bind' and tag in wanted:
                texts[tag] = (p.get('snapshot_data') or {}).get('text', '')
    for row in rows:
        text = texts.get(tuple(row['source_tag']), '')
        start, end = row['source_range']
        # Explicitly delimited source excerpt, never a generated paraphrase.
        lo, hi = max(0, start-96), min(len(text), end+96)
        row['memory_excerpt'] = text[lo:hi] if text[start:end] == row['raw'] else row['raw']
        row['memory_excerpt_range'] = [lo, hi] if text[start:end] == row['raw'] else [start, end]
        row['source_context_available'] = bool(text) and text[start:end] == row['raw']
        row['source_context'] = text if row['source_context_available'] else ''
    return rows, False


def validate_receipt(binding, journal):
    """A foreign anchor needs this interpretation's durable active-workspace read."""
    if journal is None:
        raise ValueError('SPATIAL_CONTEXT_RECEIPT_INVALID')
    records = journal.scan_unprocessed(0, payload_kinds={'run_bind', 'CONTEXT_READ'})
    owners = {r['payload']['owner'] for r in records if r['payload'].get('kind') == 'run_bind'
              and [r['payload'].get('observation_id'), r['payload'].get('version')] == binding['source_tag']}
    for record in records:
        p = record['payload']
        if p.get('kind') != 'CONTEXT_READ' or record.get('run_id') not in owners:
            continue
        request, result = p['request'], p['result']
        if (request.get('kind') != 'SPATIAL_REFERENCE'
            or request.get('decision_ref') != binding['interpretation_decision_ref']
            or p['result_hash'] != binding['context_read_hash']
            or digest(result) != p['result_hash'] or result.get('scope') != 'ACTIVE_WORKSPACE'
            or result.get('search_incomplete')):
            continue
        if any(row.get('entity_ref') == binding['target_ref']
               and row.get('memory_binding_ref') == binding['anchor_binding_ref'] for row in result['rows']):
            return
    raise ValueError('SPATIAL_CONTEXT_RECEIPT_INVALID')
