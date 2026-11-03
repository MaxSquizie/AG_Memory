#!/usr/bin/env python3
"""Audit observed TSV exchanges and budget deltas without inferring language coverage."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))

from ah.diagnostics.runtime_trace import read_events, escape_scalar
from ah.diagnostics.probe_catalog import classify_reply, resolve_slot


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def span_key(row, span_id=None):
    return (row['session_id'], row['trace_id'], row['span_id'] if span_id is None else span_id)


def trace_key(row):
    return (row['session_id'], row['trace_id'])


def catalog_identity(catalog):
    if catalog.get('schema_version') != 'probe-catalog-1':
        raise ValueError('unsupported recorded probe catalog')
    registry = {key: catalog[key] for key in ('slots', 'source_collection')}
    if digest(registry) != catalog.get('registry_sha256'):
        raise ValueError('recorded registry hash mismatch')
    body = {key: value for key, value in catalog.items() if key != 'catalog_sha256'}
    sha = digest(body)
    if catalog.get('catalog_sha256', sha) != sha:
        raise ValueError('recorded catalog hash mismatch')
    return sha


def load_runtime(path):
    """Discard large IR snapshots; retain the evidence needed for this audit."""
    keep = {'span_started', 'span_finished', 'span_failed', 'probe_catalog',
            'provider_request', 'executor_request', 'provider_receipt', 'provider_exchange',
            'selection_attempt', 'selection_protocol_validated',
            'selection_protocol_rejected', 'selection_protocol_repair_requested',
            'backend_request_context', 'budget_configured', 'budget_charged',
            'budget_window_entered', 'budget_checked', 'provider_budget_rejected',
            'executor_budget_rejected', 'trace_capture_failed', 'probe_domain', 'probe_input_contract'}
    rows = []
    counts = Counter()
    seen = set()
    for row in read_events(path):
        address = (row['session_id'], row['sequence'])
        if address in seen:
            raise ValueError('duplicate TSV event sequence: ' + repr(address))
        seen.add(address)
        counts[row['event']] += 1
        if row['event'] in keep or (row['event'] == 'syntax_trace' and
                row['data'].get('record', {}).get('kind') == 'PROBE_INPUT_CONTRACT'):
            rows.append(row)
    return {'source_sha256': file_digest(path), 'rows': rows, 'event_counts': dict(counts)}


def collect_exchanges(rows):
    """One observation per provider invocation, including replay and failed gates.

    State snapshots, protocol validation and executor delegation are never extra
    model calls. Payload delegation is followed only along the actual span ancestry.
    """
    starts = {}
    terminals = {}
    executor_payloads = {}
    receipts = defaultdict(list)
    attempts = defaultdict(list)
    contracts = defaultdict(list)
    catalogs = {}
    backend_calls = defaultdict(list)
    exchange_metadata = {}
    for row in rows:
        event, data, key = row['event'], row['data'], span_key(row)
        if event == 'span_started':
            if key in starts:
                raise ValueError('duplicate span start: ' + repr(key))
            starts[key] = row
        elif event in {'span_finished', 'span_failed'}:
            if key in terminals:
                raise ValueError('duplicate span terminal: ' + repr(key))
            terminals[key] = row
        elif event == 'executor_request':
            executor_payloads[key] = row
        elif event == 'provider_receipt':
            receipts[key].append(row)
        elif event == 'selection_attempt':
            attempts[key].append(row)
        elif event == 'probe_catalog':
            catalog = data.get('catalog', {})
            catalog_identity(catalog)
            old = catalogs.get(trace_key(row))
            if old is not None and old != catalog:
                raise ValueError('catalog changed inside one trace')
            catalogs[trace_key(row)] = catalog
        elif event == 'backend_request_context':
            backend_calls[key].append(row)
        elif event == 'provider_exchange':
            exchange_metadata[key] = data
        elif event in {'syntax_trace', 'probe_input_contract'}:
            record = data['record'] if event == 'syntax_trace' else data
            contracts[(*trace_key(row), data.get('state_ref'),
                       record.get('decision_ref'))].append(row)

    def ancestors(row):
        key, visited = span_key(row), set()
        while key in starts:
            if key in visited:
                raise ValueError('cycle in span ancestry')
            visited.add(key)
            start = starts[key]
            yield key, start
            if not start['parent_span_id']:
                break
            key = span_key(start, start['parent_span_id'])

    exchanges = []
    original_contexts = {}
    for request in (row for row in rows if row['event'] == 'provider_request'):
        data, key = request['data'], span_key(request)
        chain = list(ancestors(request))
        payload = data
        if data.get('payload_source') == 'EXECUTOR':
            payload = next((executor_payloads[k]['data'] for k, _ in chain
                            if k in executor_payloads), {})
        prompt, audit = payload.get('prompt'), payload.get('selection_audit')
        receipt_rows = receipts[key]
        if len(receipt_rows) > 1:
            raise ValueError('multiple receipts for one provider invocation')
        receipt = receipt_rows[0] if receipt_rows else None
        terminal = terminals.get(key)
        raw = receipt['data'].get('raw_response') if receipt else None
        raw_present = receipt is not None and 'raw_response' in receipt['data']
        protocol_parent = next((k for k, start in chain
                                if start['stage'] == 'SELECTION_PROTOCOL'), None)
        preceding = [r for r in attempts.get(protocol_parent, ())
                     if int(r['sequence']) < int(request['sequence'])]
        attempt = preceding[-1]['data'].get('attempt') if preceding else None
        is_replay = bool(receipt and receipt['status'].startswith('REPLAYED_'))
        transport_error = (receipt['reason'] or 'recorded provider failure') if receipt and receipt['status'] == 'REPLAYED_FAILED' else None
        if not raw_present and terminal and terminal['status'] == 'UNAVAILABLE':
            transport_error = terminal['reason'] or 'provider unavailable'
        classification = classify_reply(raw, audit=audit, prompt=prompt,
            prompt_complete=isinstance(prompt, str), response_present=raw_present,
            provider_error=transport_error, unfinished=terminal is None and receipt is None)
        blocked = bool(terminal and terminal['status'] == 'BLOCKED')
        if blocked and not raw_present:
            classification = {**classification, 'outcome': 'BUDGET_BLOCKED',
                              'reason': terminal['reason']}
        raw_slot = audit.get('slot') if isinstance(audit, dict) else data.get('slot')
        raw_slot = raw_slot or 'UNDECLARED_SLOT'
        contract_rows = contracts.get((*trace_key(request), data.get('state_ref'),
                                       data.get('decision_ref')), ())
        contract_rows = [r for r in contract_rows if int(r['sequence']) <= int(request['sequence'])]
        contract_row = contract_rows[-1] if contract_rows else None
        contract_data = contract_row['data'] if contract_row else {}
        declared = contract_data.get('record', contract_data).get('semantic_contract')
        catalog = catalogs.get(trace_key(request))
        slot = resolve_slot(raw_slot, catalog=catalog or {'slots': {}, 'aliases': {}},
                            declared_contract=declared)
        request_kind = ('EMBEDDING_RANKING' if any(start['stage'] == 'LEXICAL_EMBEDDING_RANK' for _, start in chain)
                        else data.get('request_kind', 'UNSPECIFIED_TRANSPORT'))
        address = {name: request[name] for name in
                   ('session_id', 'trace_id', 'span_id', 'sequence')}
        metadata = exchange_metadata.get(key, {})
        effective_params = metadata.get('params_hash')
        backend_context = [{field: call['data'].get(field) for field in
            ('backend_type', 'model_key', 'system', 'role', 'generation_settings',
             'selection_reply_format', 'structure_reply_format')}
            for call in backend_calls[key]]
        call_identity = (receipt['entity_id'], request['run_id'], metadata.get('request_digest'),
                         metadata.get('model_key'), effective_params,
                         digest({'prompt': prompt, 'selection_audit': audit})) if receipt else None
        context_source = 'CAPTURED_CALL' if backend_context else 'NOT_RECORDED'
        if backend_context and call_identity:
            original_contexts[call_identity] = backend_context
        elif is_replay and call_identity in original_contexts:
            backend_context = original_contexts[call_identity]
            context_source = 'REPLAY_ORIGINAL_IN_TRACE'
        payload_binding = {'prompt': prompt, 'selection_audit': audit,
                           'backend_input_context': backend_context,
                           'model_key': metadata.get('model_key', data.get('model_key')),
                           'params_hash': effective_params}
        exchanges.append({
            'event_address': address, 'sample_id': digest(address),
            'payload_sha256': digest(payload_binding),
            'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest() if isinstance(prompt, str) else None,
            'prompt': prompt, 'selection_audit': audit, 'raw_response': raw,
            'backend_input_context': backend_context, 'backend_context_source': context_source,
            'backend_context_sha256': digest(backend_context) if backend_context else None,
            'classification': classification, 'slot': slot,
            'catalog_sha256': catalog_identity(catalog) if catalog else None,
            'pipeline_stage': data.get('pipeline_stage', 'UNKNOWN'),
            'case_id': data.get('case_id'), 'state_ref': data.get('state_ref'),
            'condition_ref': data.get('condition_ref'), 'decision_ref': data.get('decision_ref'),
            'run_id': request['run_id'], 'model_key': metadata.get('model_key', data.get('model_key')),
            'params_hash': effective_params, 'base_params_hash': data.get('params_hash'),
            'operation': data.get('operation'),
            'request_kind': request_kind,
            'protocol_attempt': attempt, 'replay': is_replay,
            'protocol_span_id': protocol_parent[-1] if protocol_parent else None,
            'sample_kind': 'REPLAY' if is_replay else 'FORMAT_REPAIR' if attempt is not None and attempt > 0
                           else 'INITIAL' if attempt == 0 else 'UNSCOPED',
            'physical_generation_requests': len(backend_calls[key]),
            'terminal_status': terminal['status'] if terminal else None,
            'terminal_reason': terminal['reason'] if terminal else None,
            'response_received': raw_present, 'blocked_after_receipt': blocked and raw_present,
        })
    return exchanges


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def unscored_boundaries(rows, exchanges):
    """Expose execution paths that did not use the ProviderAdapter boundary."""
    starts = {span_key(row): row for row in rows if row['event'] == 'span_started'}
    covered = set()
    for item in exchanges:
        address = item['event_address']
        key = (address['session_id'], address['trace_id'], address['span_id'])
        visited = set()
        while key in starts and key not in visited:
            visited.add(key)
            covered.add(key)
            start = starts[key]
            if not start['parent_span_id']:
                break
            key = span_key(start, start['parent_span_id'])
    executor_keys = {span_key(row) for row in rows if row['event'] == 'executor_request'}
    protocol_keys = {key for key, row in starts.items() if row['stage'] == 'SELECTION_PROTOCOL'}
    return {'executor_requests_without_provider': len(executor_keys - covered),
            'selection_protocols_without_provider': len(protocol_keys - covered)}


def summarize(loaded):
    rows = loaded['rows']
    exchanges = collect_exchanges(rows)
    groups = defaultdict(Counter)
    for item in exchanges:
        if item['operation'] != 'select' or item['request_kind'] == 'EMBEDDING_RANKING':
            continue
        slot = item['slot']
        key = (item['catalog_sha256'] or 'NOT_RECORDED', item['pipeline_stage'],
               slot['raw_slot'], slot['canonical_slot'], slot.get('family') or 'UNDECLARED',
               item['sample_kind'], item['model_key'] or 'NOT_RECORDED',
               item['params_hash'] or 'NOT_RECORDED', item['backend_context_sha256'] or 'NOT_RECORDED')
        groups[key]['provider_invocations'] += 1
        groups[key][item['classification']['outcome']] += 1
    probe_rows = []
    for key, counts in sorted(groups.items()):
        selected = counts['CHOSEN_ONE'] + counts['CHOSEN_MULTIPLE']
        valid = selected + counts['NONE_FIT'] + counts['INSUFFICIENT_CONTEXT']
        probe_rows.append(dict(zip(('catalog_sha256', 'pipeline_stage', 'raw_slot',
            'canonical_slot', 'family', 'sample_kind', 'model_key', 'params_hash',
            'backend_context_sha256'), key), counts=dict(counts),
            valid_wire_responses=valid,
            positive_selection_fraction=ratio(selected, valid),
            abstention_fraction=ratio(counts['INSUFFICIENT_CONTEXT'], valid),
            semantic_accuracy='NOT_EVALUATED'))
    budget_groups = defaultdict(Counter)
    configurations = []
    for row in rows:
        data = row['data']
        if row['event'] == 'budget_configured':
            configurations.append({'event_address': {name: row[name] for name in
                ('session_id', 'trace_id', 'span_id', 'sequence')}, **data})
        elif row['event'] == 'budget_charged':
            key = (*trace_key(row), str(data.get('budget_ref', 'UNKNOWN')),
                   str(data.get('budget_epoch', 'UNKNOWN')),
                   data.get('budget_level', 'UNKNOWN'), data.get('scope', 'UNKNOWN'),
                   str(data.get('window_key') or ''), data.get('pipeline_stage', 'UNKNOWN'),
                   data.get('replay'))
            for counter, value in data.get('delta', {}).items():
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError('non-numeric budget delta')
                budget_groups[key][counter] += value
    budget_rows = [dict(zip(('session_id', 'trace_id', 'budget_ref', 'budget_epoch',
        'budget_level', 'scope', 'window_key', 'pipeline_stage', 'replay'), key),
        delta=dict(counts)) for key, counts in sorted(budget_groups.items(), key=lambda pair: tuple(map(str, pair[0])))]
    catalog_groups = {}
    catalog_by_trace = {}
    for row in rows:
        if row['event'] != 'probe_catalog':
            continue
        catalog = row['data']['catalog']
        catalog_groups[catalog_identity(catalog)] = catalog
        catalog_by_trace[trace_key(row)] = catalog
    slot_boundaries = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        is_protocol = row['event'] == 'span_started' and row['stage'] == 'SELECTION_PROTOCOL'
        if not is_protocol and row['event'] != 'probe_domain':
            continue
        catalog = catalog_by_trace.get(trace_key(row))
        if catalog is None:
            continue
        raw_slot = row['data'].get('slot') or 'UNDECLARED_SLOT'
        canonical = resolve_slot(raw_slot, catalog=catalog)['canonical_slot']
        slot_boundaries[catalog_identity(catalog)][canonical][
            'observed_selection_protocols' if is_protocol else 'observed_probe_entries'] += 1
    coverage = []
    for sha, catalog in sorted(catalog_groups.items()):
        observed = Counter(e['slot']['canonical_slot'] for e in exchanges if e['catalog_sha256'] == sha)
        for slot, contract in sorted(catalog['slots'].items()):
            boundaries = slot_boundaries[sha][slot]
            status = ('OBSERVED' if observed[slot] else 'OBSERVED_PROTOCOL_ONLY'
                      if boundaries['observed_selection_protocols'] else 'OBSERVED_NO_SELECTION_EXCHANGE'
                      if boundaries['observed_probe_entries'] else 'NOT_OBSERVED_IN_EXPORT')
            coverage.append({'catalog_sha256': sha, 'slot': slot, 'family': contract['family'],
                'observed_provider_invocations': observed[slot],
                **dict(boundaries), 'status': status,
                'language_support': 'NOT_EVALUATED'})
        for slot in sorted((set(observed) | set(slot_boundaries[sha])) - set(catalog['slots'])):
            views = [e['slot'] for e in exchanges if e['catalog_sha256'] == sha and e['slot']['canonical_slot'] == slot]
            dynamic = bool(views) and all(view['registry_status'] == 'DYNAMIC_SOURCE_COLLECTION' for view in views)
            families = sorted({view['family'] for view in views if view.get('family')})
            coverage.append({'catalog_sha256': sha, 'slot': slot, 'family': ','.join(families) or 'UNDECLARED',
                'observed_provider_invocations': observed[slot],
                **dict(slot_boundaries[sha][slot]),
                'status': 'DYNAMIC_SOURCE_COLLECTION' if dynamic else 'UNREGISTERED_OBSERVED',
                'language_support': 'NOT_EVALUATED'})
    started = {span_key(r) for r in rows if r['event'] == 'span_started'}
    ended = {span_key(r) for r in rows if r['event'] in {'span_finished', 'span_failed'}}
    protocols = {}
    for row in rows:
        data, key = row['data'], span_key(row)
        if row['event'] == 'span_started' and row['stage'] == 'SELECTION_PROTOCOL':
            protocols[key] = {'session_id': row['session_id'], 'trace_id': row['trace_id'],
                'span_id': row['span_id'], 'raw_slot': data.get('slot'),
                'pipeline_stage': data.get('pipeline_stage', 'UNKNOWN'),
                'decision_ref': data.get('decision_ref', row['entity_id']),
                'state_ref': data.get('state_ref'), 'condition_ref': data.get('condition_ref'),
                'attempts': 0, 'format_repairs': 0, 'validated_outcome': None,
                'terminal_status': None, 'terminal_reason': None}
        if key not in protocols:
            continue
        record = protocols[key]
        if row['event'] == 'selection_attempt':
            record['attempts'] += 1
        elif row['event'] == 'selection_protocol_repair_requested':
            record['format_repairs'] += 1
        elif row['event'] == 'selection_protocol_validated':
            record['validated_outcome'] = data.get('selector_outcome')
        elif row['event'] in {'span_finished', 'span_failed'}:
            record.update(terminal_status=row['status'], terminal_reason=row['reason'])
    for key, record in protocols.items():
        record['provider_invocations'] = sum(e['event_address']['session_id'] == key[0]
            and e['event_address']['trace_id'] == key[1] and e['protocol_span_id'] == key[2] for e in exchanges)
    return {'schema_version': 'runtime-probe-audit-1', 'source_sha256': loaded['source_sha256'],
        'event_counts': loaded['event_counts'], 'provider_invocations': len(exchanges),
        'physical_generation_requests': sum(r['event'] == 'backend_request_context' for r in rows),
        'probe_metrics': probe_rows, 'budget_metrics': budget_rows,
        'budget_configurations': configurations, 'coverage': coverage,
        'selection_protocols': list(protocols.values()),
        'catalogs': list(catalog_groups.values()),
        'evidence_gaps': {'started_spans_without_terminal': len(started - ended),
            'terminals_without_start': len(ended - started),
            'exchanges_without_catalog': sum(e['catalog_sha256'] is None for e in exchanges),
            'exchanges_without_prompt': sum(not isinstance(e['prompt'], str) for e in exchanges),
            'trace_capture_failures': loaded['event_counts'].get('trace_capture_failed', 0),
            **unscored_boundaries(rows, exchanges)},
        'claims': {'semantic_accuracy': 'NOT_EVALUATED', 'language_coverage': 'NOT_EVALUATED',
                   'model_confidence': 'NOT_MEASURED', 'g5_holdout_claim': False},
        'accounting': 'Budget deltas are summed only within one level, owner, epoch and window. '
                      'Provider estimates, selector attempts, executor calls and physical generation are separate. '
                      'No state snapshots are counted as new work. A null replay value means the level '
                      'did not record replay attribution; it does not mean a fresh physical request.'}


def write_table(path, rows, columns):
    def cell(value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return '' if value is None else str(value)
    with Path(path).open('x', encoding='utf-8', newline='') as out:
        out.write('\t'.join(columns) + '\n')
        for row in rows:
            out.write('\t'.join(escape_scalar(cell(row.get(c))) for c in columns) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    report = summarize(load_runtime(args.runtime))
    if args.out.exists() and any(args.out.iterdir()):
        parser.error('output directory must be empty')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_table(args.out / 'probes.tsv', report['probe_metrics'],
        ('catalog_sha256', 'pipeline_stage', 'raw_slot', 'canonical_slot', 'family', 'sample_kind',
         'model_key', 'params_hash', 'backend_context_sha256', 'counts', 'valid_wire_responses',
         'positive_selection_fraction', 'abstention_fraction', 'semantic_accuracy'))
    write_table(args.out / 'budgets.tsv', report['budget_metrics'],
        ('session_id', 'trace_id', 'budget_ref', 'budget_epoch', 'budget_level', 'scope', 'window_key',
         'pipeline_stage', 'replay', 'delta'))
    write_table(args.out / 'coverage.tsv', report['coverage'],
        ('catalog_sha256', 'slot', 'family', 'observed_provider_invocations', 'observed_selection_protocols',
         'observed_probe_entries', 'status', 'language_support'))
    print(json.dumps({'provider_invocations': report['provider_invocations'],
                      'evidence_gaps': report['evidence_gaps']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
