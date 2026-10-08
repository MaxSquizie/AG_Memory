"""Durable speaker choices over already validated native candidates.

These records are interpretation grounds, never world facts. A selection
reserves v+1 and reuses the original input; T6 owns replacement/supersede.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
import re

from .canonical_ledger import digest


def choice(state, decision_ref, candidates):
    selected = state.observation.get('clarification_choices', {}).get(decision_ref)
    if selected is not None and selected not in candidates:
        raise ValueError('CLARIFICATION_CANDIDATE_STALE')
    return selected


def offer(state, decision_ref, kind, mention, options):
    """A finite closed set, retained even when no candidate is grounded enough."""
    if len(options) < 2:
        return
    row = {'decision_ref': decision_ref, 'kind': kind, 'mention': mention,
           'options': deepcopy(options)}
    if row not in state.clarification_candidates:
        state.clarification_candidates.append(row)


def hypothesis_json(hypothesis):
    raw = asdict(hypothesis)
    for edge in raw['edges']:
        edge['from'] = edge.pop('from_idx')
        edge['to'] = edge.pop('to_idx')
    return json.loads(json.dumps(raw))


def structure_label(state, hypothesis):
    spans = {e.token_id: e.span for e in state.evidence}
    def name(index):
        n = hypothesis.nodes[index]
        return ' '.join(spans[a] for a in n.anchor_spans)
    rows = [f"{name(e.from_idx)}: {e.role_id or e.kind} = {name(e.to_idx)}"
            for e in hypothesis.edges]
    return '; '.join(rows) or ' '.join(name(i) for i in range(len(hypothesis.nodes)))


def choose_structures(state, accepted, *, stage, provenance=None):
    """Resolve only overlapping hypotheses; independent clauses survive."""
    remaining = list(accepted)
    out = []
    while remaining:
        group = [remaining.pop(0)]
        def affected(pair):
            return {f.predicate_token_ref for f in pair[1]} or set(pair[0].alignment)
        anchors = affected(group[0])
        changed = True
        while changed:
            changed = False
            for pair in list(remaining):
                if anchors.intersection(affected(pair)):
                    group.append(pair); remaining.remove(pair)
                    anchors.update(affected(pair)); changed = True
        if len(group) == 1:
            out.extend(group); continue
        key = 'structure:' + stage + ':' + digest(sorted(h.local_id for h, _ in group))
        ids = [h.local_id for h, _ in group]
        selected = choice(state, key, ids)
        if selected is None:
            offer(state, key, 'STRUCTURE', ' / '.join(structure_label(state, h) for h, _ in group),
                  [{'candidate_id': h.local_id, 'label': structure_label(state, h),
                    'hypothesis': hypothesis_json(h), 'stage': stage,
                    'morph_bindings': deepcopy(frames[0].semantic.get('morph_bindings',{})) if frames else {},
                    'provenance': asdict((provenance or {}).get(h.local_id) or h_provenance(frames))}
                   for h, frames in group])
            out.extend(group)
        else:
            state.syntax_trace.append({'stage': 'TD', 'event': 'SPEAKER_CHOICE',
                                       'decision_ref': key, 'selected': selected})
            for h, frames in group:
                if h.local_id == selected:
                    out.append((h, frames))
                else:
                    state.reject(h.local_id, 'CLARIFICATION', 'explicit speaker selection: ' + selected,
                                 (provenance or {}).get(h.local_id))
    return out


def h_provenance(frames):
    from .state import ResourceProvenance
    return frames[0].provenance if frames else ResourceProvenance()


def persist_offers(state, store, binding, release):
    from ah.perception.contracts import StructuralClarificationOption, StructuralClarificationSpec
    result = []
    with binding._lock, store._journal.atomic():
        frozen = binding.input_snapshot(state.source_uid, state.interpretation_version)
        if frozen is None:
            raise ValueError('CLARIFICATION_INPUT_MISSING')
        existing = {r['payload']['request_id']: r['payload'] for r in store._journal.scan_unprocessed()
                    if r['payload'].get('kind') == 'CLARIFICATION_REQUEST'}
        for row in state.clarification_candidates:
            options = sorted(deepcopy(row['options']), key=lambda x: x['candidate_id'])
            if len({x['candidate_id'] for x in options}) != len(options):
                raise ValueError('CLARIFICATION_DUPLICATE_CANDIDATE')
            body = {'observation_id': state.source_uid, 'version': state.interpretation_version,
                    'input_sha256': digest(frozen), 'resource_snapshot': release.sha256,
                    'decision_ref': row['decision_ref'], 'ambiguity_type': row['kind'],
                    'mention': row['mention'], 'source_text': state.text, 'options': options}
            body['generation_snapshot'] = deepcopy(state.generation_snapshot)
            rid = digest(body)
            record = {'kind': 'CLARIFICATION_REQUEST', 'request_id': rid, **body}
            if rid in existing and existing[rid] != record:
                raise ValueError('INTEGRITY_ERROR: clarification request changed')
            if rid not in existing:
                store._journal.append('resolution_log', record)
            result.append(StructuralClarificationSpec(
                row['kind'], row['mention'], state.text,
                tuple(StructuralClarificationOption('v7:' + rid + ':' + digest(o), o['label']) for o in options)))
    return tuple(result)


def validate_input(store, observation):
    """Raw clients cannot introduce an unlogged choice or a new hypothesis."""
    choices = observation.get('clarification_choices', {})
    structures = observation.get('clarification_structures', {})
    if not choices and not structures and not observation.get('clarification_generation'):
        return
    sid = observation.get('clarification_selection_ref')
    records = [r['payload'] for r in store._journal.scan_unprocessed()
               if r['payload'].get('kind') == 'CLARIFICATION_SELECTED' and r['payload'].get('selection_id') == sid]
    if len(records) != 1:
        raise ValueError('CLARIFICATION_SELECTION_MISSING')
    record = records[0]
    request = next((r['payload'] for r in store._journal.scan_unprocessed()
                    if r['payload'].get('kind') == 'CLARIFICATION_REQUEST'
                    and r['payload'].get('request_id') == record['request_id']), None)
    if request is None or request['source_text'] != observation['text']:
        raise ValueError('CLARIFICATION_INPUT_MISMATCH')
    inherited = observation['interpretation_version'] > record['target_version']
    if (record['observation_id'] != observation['observation_id']
            or record['target_version'] > observation['interpretation_version']
            or record['input_changes']['clarification_choices'] != choices
            or record['input_changes']['clarification_structures'] != structures
            or record['input_changes'].get('clarification_generation') != observation.get('clarification_generation')
            or not inherited and record['selection_id'] != observation.get('trigger_ref')):
        raise ValueError('CLARIFICATION_SELECTION_MISMATCH')
    if inherited:
        from .run_binding import InterpretationRunBinding
        previous = InterpretationRunBinding(store._journal).input_snapshot(
            observation['observation_id'], observation.get('supersedes_version'))
        if previous is None or any(previous.get(k) != observation.get(k) for k in (
                'clarification_choices', 'clarification_structures', 'clarification_selection_ref', 'clarification_generation')):
            raise ValueError('CLARIFICATION_SELECTION_MISMATCH')


def resolve(adapter, resolution_key, *, source_text=None):
    """Replay a durable choice, or reserve one fresh replacement version."""
    from .migration import reinterpret_observation
    match = re.fullmatch(r'v7:([0-9a-f]{64}):([0-9a-f]{64})', resolution_key)
    if match is None:
        raise ValueError('CLARIFICATION_KEY_INVALID')
    rid, option_hash = match.groups()
    store, binding, release = adapter._store, adapter._binding, adapter._release
    with binding._lock, store._journal.atomic(), store._store._lock:
        store._refresh()
        records = [r['payload'] for r in store._journal.scan_unprocessed()]
        requests = [r for r in records if r.get('kind') == 'CLARIFICATION_REQUEST' and r.get('request_id') == rid]
        if len(requests) != 1:
            raise ValueError('CLARIFICATION_REQUEST_MISSING')
        request = requests[0]
        if source_text is not None and request['source_text'] != source_text:
            raise ValueError('CLARIFICATION_INPUT_MISMATCH')
        if request['resource_snapshot'] != release.sha256:
            raise ValueError('CLARIFICATION_RESOURCE_STALE')
        options = [o for o in request['options'] if digest(o) == option_hash]
        if len(options) != 1:
            raise ValueError('CLARIFICATION_OPTION_INVALID')
        oid, previous = request['observation_id'], request['version']
        frozen = binding.input_snapshot(oid, previous)
        if frozen is None or digest(frozen) != request['input_sha256']:
            raise ValueError('CLARIFICATION_INPUT_CHANGED')
        old = [r for r in records if r.get('kind') == 'CLARIFICATION_SELECTED' and r.get('request_id') == rid]
        if old:
            if len(old) != 1 or old[0]['option_hash'] != option_hash:
                raise ValueError('CLARIFICATION_ALREADY_SELECTED')
            selected = old[0]
        else:
            # No stale H choice can supersede a newer interpretation.
            if max(binding.versions(oid), default=previous) != previous:
                raise ValueError('CLARIFICATION_VERSION_STALE')
            obs = store.ledger.data['observations'].get(digest([oid, previous]))
            if obs is not None and obs['status'] != 'LIVE':
                raise ValueError('CLARIFICATION_SOURCE_STALE')
            option = options[0]
            choices = deepcopy(frozen.get('clarification_choices', {}))
            choices[request['decision_ref']] = option['candidate_id']
            structures = deepcopy(frozen.get('clarification_structures', {}))
            if option.get('stage') == 'TP':
                structures[request['decision_ref']] = deepcopy(option['hypothesis'])
            sid = 'clarification:' + digest([rid, option_hash])
            changes = {'clarification_choices': choices, 'clarification_structures': structures,
                       'clarification_selection_ref': sid}
            if request.get('generation_snapshot'):
                changes['clarification_generation'] = deepcopy(request['generation_snapshot'])
            selected = {'kind': 'CLARIFICATION_SELECTED', 'selection_id': sid, 'request_id': rid,
                        'option_hash': option_hash, 'observation_id': oid, 'previous_version': previous,
                        'target_version': previous + 1, 'run_id': 'run:' + digest([sid, previous + 1]),
                        'input_changes': changes}
            store._journal.append('resolution_log', selected)
    state, report = reinterpret_observation(
        store, binding, adapter._selector, release, observation_id=oid,
        previous_version=previous, target_version=selected['target_version'],
        run_id=selected['run_id'], trigger_ref=selected['selection_id'],
        input_changes=selected['input_changes'], morph=adapter._morph)
    return state, report


def request_current(adapter, resolution_key):
    match = re.fullmatch(r'v7:([0-9a-f]{64}):([0-9a-f]{64})', resolution_key)
    if match is None:
        return False
    records = [r['payload'] for r in adapter._store._journal.scan_unprocessed()]
    request = next((r for r in records if r.get('kind') == 'CLARIFICATION_REQUEST'
                    and r.get('request_id') == match[1]), None)
    if request is None or request['resource_snapshot'] != adapter._release.sha256:
        return False
    with adapter._store._journal.atomic(), adapter._store._store._lock:
        adapter._store._refresh()
        observation = adapter._store.ledger.data['observations'].get(digest([request['observation_id'], request['version']]))
        if observation is not None and observation['status'] != 'LIVE':
            return False
    if any(r.get('kind') == 'CLARIFICATION_COMPLETED' and r.get('request_id') == request['request_id'] for r in records):
        return False
    versions=[r.get('version') for r in records if r.get('kind')=='run_bind' and r.get('observation_id')==request['observation_id']]
    versions.extend(r['target_version'] for r in records if r.get('kind')=='CLARIFICATION_SELECTED' and r.get('observation_id')==request['observation_id'])
    versions.extend(i['target_version'] for r in records if r.get('kind')=='MIGRATION_PLANNED' for i in r['items'] if i['observation_id']==request['observation_id'])
    latest = max(versions, default=request['version'])
    if latest == request['version']:
        return True
    return any(r.get('kind') == 'CLARIFICATION_SELECTED' and r.get('request_id') == request['request_id']
               and r.get('target_version') == latest for r in records)
