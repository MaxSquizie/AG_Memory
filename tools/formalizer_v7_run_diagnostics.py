#!/usr/bin/env python3
"""Inspect actual V7 run diagnostics, including interrupted GUI runs.

Read-only: no corpus/gold, model invocation, replay or canonical writes. A first
recorded diagnostic is evidence, not a claim that its causal origin is proven.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import gzip
import hashlib
import json

TEXT_LIMIT = 1600
ITEM_LIMIT = 32


def _text(value, limit=TEXT_LIMIT):
    if isinstance(value, str):
        return value[:limit]
    return json.dumps(value, ensure_ascii=False, default=str)[:limit]


def _case_digest(case_id):
    return hashlib.sha256(json.dumps(case_id, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _jsonl(path, warnings):
    """Keep complete rows before a torn final append or gzip interruption."""
    path = Path(path)
    if not path.is_file():
        return
    opener = gzip.open if path.suffix == '.gz' else open
    try:
        with opener(path, 'rt', encoding='utf-8') as source:
            for number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    warnings.append(f'{path.name}:{number}: incomplete/invalid JSON record')
                    continue
                if isinstance(row, dict):
                    yield number, row
    except (OSError, EOFError, UnicodeError) as exc:
        warnings.append(f'{path.name}: {_text(exc)}')


def _prompt_stage(prompt):
    """Only use an explicit request identifier, never a guessed code mapping."""
    try:
        data = json.loads(prompt)
        request_id = data.get('request', {}).get('request_id')
        if isinstance(request_id, str) and request_id.startswith('TP:'):
            return 'TP', 'provider prompt /request/request_id'
    except (TypeError, ValueError, AttributeError):
        pass
    return 'NOT_RECORDED', None


def case_diagnostics(actual, *, wal_path=None, progress_events=()):
    """Extract actual native diagnostics/report and transport/WAL failures.

    This function does not receive a gold case or comparator expectations.
    Output is bounded and may be attached to a ``case_finished`` event.
    """
    actual = actual or {}
    warnings = []
    diagnostics, reports, provider_errors, provider_replies = [], [], [], []
    seen = set()

    def collect(observed, step_id, prefix):
        if not isinstance(observed, dict):
            return
        runtime = observed.get('runtime') or {}
        if not isinstance(runtime, dict):
            return
        ir = runtime.get('ir') or {}
        if isinstance(ir, dict):
            for index, row in enumerate(ir.get('diagnostics') or []):
                if not isinstance(row, dict):
                    continue
                code, detail = row.get('code'), row.get('detail', '')
                key = (step_id, str(code), str(detail))
                if key in seen:
                    continue
                seen.add(key)
                diagnostics.append({'code': _text(code), 'detail': _text(detail),
                    'step_id': step_id, 'stage': row.get('stage') or 'NOT_RECORDED',
                    'path': f'{prefix}/runtime/ir/diagnostics/{index}'})
        report = runtime.get('report')
        if isinstance(report, dict):
            reports.append({'step_id': step_id, 'path': prefix + '/runtime/report',
                **{k: report.get(k) for k in ('terminal', 't5_eligibility', 'binding_ok',
                     'applied', 'observation_id', 'version', 'batch_hash') if k in report}})

    for index, checkpoint in enumerate(actual.get('checkpoints') or []):
        if isinstance(checkpoint, dict):
            collect(checkpoint.get('actual'), checkpoint.get('step_id'), f'/checkpoints/{index}/actual')

    starts = {}
    for row in progress_events:
        if not isinstance(row, dict):
            continue
        if row.get('event') == 'request_started':
            starts[row.get('request_id')] = row
        elif row.get('event') == 'request_finished' and (row.get('error') or row.get('status') == 'ERROR'):
            started = starts.get(row.get('request_id'), {})
            stage, evidence = _prompt_stage(started.get('prompt'))
            provider_errors.append({'source': 'progress.jsonl', 'seq': row.get('seq'),
                'request_id': row.get('request_id'), 'step_id': row.get('step_id', started.get('step_id')),
                'provider': row.get('provider', started.get('provider')), 'stage': stage,
                'stage_evidence': evidence, 'error': _text(row.get('error', 'request ERROR')),
                'http_status': row.get('http_status')})
        elif row.get('event') == 'step_finished':
            collect(row.get('actual'), row.get('step_id'), f'/progress/seq/{row.get("seq")}/actual')
        if row.get('event') == 'request_finished' and isinstance(row.get('response'), str):
            started = starts.get(row.get('request_id'), {})
            stage, evidence = _prompt_stage(started.get('prompt'))
            reply = row['response']
            provider_replies.append({'source': 'progress.jsonl visible response',
                'request_id': row.get('request_id'), 'seq': row.get('seq'), 'stage': stage,
                'stage_evidence': evidence, 'response': reply[:TEXT_LIMIT],
                'response_chars': row.get('response_chars', len(reply)),
                'truncated': len(reply) > TEXT_LIMIT or bool(row.get('response_truncated'))})

    if wal_path:
        for line, row in _jsonl(wal_path, warnings):
            payload = row.get('payload') or {}
            if not isinstance(payload, dict) or payload.get('kind') != 'prov_call':
                continue
            stage, evidence = _prompt_stage(payload.get('prompt'))
            if payload.get('state') == 'FAILED':
                provider_errors.append({'source': 'provider WAL', 'path': f'{Path(wal_path).name}:{line}',
                    'seq': row.get('seq'), 'provider': payload.get('provider'),
                    'call_id': payload.get('id'), 'ordinal': payload.get('ordinal'),
                    'attempt': payload.get('attempt'), 'stage': stage, 'stage_evidence': evidence,
                    'error': _text(payload.get('error', 'provider FAILED'))})
            elif payload.get('state') == 'RECEIVED' and isinstance(payload.get('raw_response'), str):
                reply = payload['raw_response']
                provider_replies.append({'source': 'provider WAL raw_response',
                    'path': f'{Path(wal_path).name}:{line}', 'seq': row.get('seq'),
                    'call_id': payload.get('id'), 'ordinal': payload.get('ordinal'),
                    'stage': stage, 'stage_evidence': evidence, 'response': reply[:TEXT_LIMIT],
                    'response_chars': len(reply), 'truncated': len(reply) > TEXT_LIMIT,
                    'response_sha256': hashlib.sha256(reply.encode()).hexdigest()})

    exception = actual.get('runtime_error')
    runtime_error = ({'type': exception.get('type'), 'message': _text(exception.get('message', ''))}
                     if isinstance(exception, dict) else None)
    # Keep each source's actual order. Cross-source order is not invented: WAL
    # and native diagnostics do not necessarily share event sequence numbers.
    first = None
    if provider_errors:
        first = {'kind': 'PROVIDER_ERROR', **provider_errors[0]}
    elif runtime_error:
        first = {'kind': 'RUNTIME_EXCEPTION', 'stage': 'NOT_RECORDED', **runtime_error}
    elif diagnostics:
        first = {'kind': 'RUNTIME_DIAGNOSTIC', **diagnostics[0]}
    result = {'case_id': actual.get('case_id'), 'first_observed_issue': first,
        'native_diagnostics': diagnostics[:ITEM_LIMIT], 'native_reports': reports[:ITEM_LIMIT],
        'provider_errors': provider_errors[:ITEM_LIMIT], 'provider_replies': provider_replies[:ITEM_LIMIT],
        'provider_reply_record_count': len(provider_replies), 'runtime_error': runtime_error,
        'omitted': {'native_diagnostics': max(0, len(diagnostics) - ITEM_LIMIT),
                    'native_reports': max(0, len(reports) - ITEM_LIMIT),
                    'provider_errors': max(0, len(provider_errors) - ITEM_LIMIT),
                    'provider_replies': max(0, len(provider_replies) - ITEM_LIMIT)},
        'artifact_warnings': warnings[:ITEM_LIMIT],
        'causal_attribution': 'NOT_INFERRED'}
    result['first_observed_text'] = first_issue_text(result)
    result['native_diagnostic_text'] = ' | '.join(
        f"{d['code']}: {d['detail']}" for d in diagnostics[:8])[:4000]
    return result


def first_issue_text(diagnostics):
    """Plain text for the GUI; callers must HTML-escape it."""
    if not isinstance(diagnostics, dict):
        return ''
    issue = diagnostics.get('first_observed_issue')
    if not isinstance(issue, dict):
        return 'Runtime: диагностическая причина в артефактах не записана.'
    stage = issue.get('stage', 'NOT_RECORDED')
    location = issue.get('step_id') or issue.get('path') or issue.get('source') or ''
    if issue.get('kind') == 'RUNTIME_DIAGNOSTIC':
        detail = f"{issue.get('code')}: {issue.get('detail', '')}"
        heading = 'Первая записанная диагностика'
    else:
        detail = str(issue.get('error') or issue.get('message') or '')
        heading = 'Записанная ошибка провайдера' if issue.get('kind') == 'PROVIDER_ERROR' else 'Runtime exception'
    return f'{heading} [{stage}; {location}]: {detail}'


def inspect_run(run_dir, *, limit=50):
    """Inspect completed and in-flight cases without requiring final reports."""
    root = Path(run_dir)
    warnings = []
    plain, archive = root / 'actual.jsonl', root / 'actual.jsonl.gz'
    path = plain if plain.is_file() else archive
    actuals = {}
    for _, row in _jsonl(path, warnings):
        if isinstance(row.get('case_id'), str):
            actuals[row['case_id']] = row
    events = {}
    run_finished = False
    for _, row in _jsonl(root / 'progress.jsonl', warnings):
        run_finished |= row.get('event') == 'run_finished'
        cid = row.get('case_id')
        if not isinstance(cid, str):
            continue
        relevant = row.get('event') in {'case_started', 'case_finished', 'request_started', 'request_finished', 'step_finished'}
        if relevant:
            events.setdefault(cid, []).append(row)
    ids = list(dict.fromkeys([*actuals, *events]))
    cases = []
    first_counts, diagnostic_counts, statuses = Counter(), Counter(), Counter()
    provider_case_count = 0
    for cid in ids:
        actual = actuals.get(cid, {'case_id': cid, 'execution_status': 'INCOMPLETE', 'checkpoints': []})
        summary = case_diagnostics(actual, wal_path=root / 'cases' / _case_digest(cid) / 'journal.log',
                                   progress_events=events.get(cid, ()))
        terminal = next((e.get('status') for e in reversed(events.get(cid, ())) if e.get('event') == 'case_finished'), None)
        summary['recorded_status'] = terminal or actual.get('execution_status', 'INCOMPLETE')
        statuses[summary['recorded_status']] += 1
        provider_case_count += bool(summary['provider_errors'])
        first = summary['first_observed_issue']
        if first:
            first_counts[first.get('code') or first.get('kind')] += 1
        diagnostic_counts.update({d['code'] for d in summary['native_diagnostics']})
        if len(cases) < limit:
            cases.append(summary)
        warnings.extend(summary['artifact_warnings'])
    return {'schema_version': 'v7-run-diagnostics-1', 'run_dir': str(root),
        'completion': 'RUN_FINISHED_RECORDED' if run_finished else 'FINAL_EVENT_NOT_RECORDED',
        'cases_observed': len(ids), 'cases_with_actual_record': len(actuals),
        'recorded_status_counts': dict(statuses), 'first_issue_case_counts': dict(first_counts),
        'native_diagnostic_case_counts': dict(diagnostic_counts),
        'cases_with_provider_errors': provider_case_count, 'cases': cases,
        'omitted_cases': max(0, len(ids) - limit), 'artifact_warnings': warnings[:ITEM_LIMIT],
        'causal_attribution': 'NOT_INFERRED', 'comparison_or_gates_re_evaluated': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path, help='GUI run directory, including an interrupted run')
    parser.add_argument('--limit', type=int, default=50, help='maximum case details (all cases count toward totals)')
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > 1000:
        parser.error('--limit must be 1..1000')
    if not args.run_dir.is_dir():
        parser.error('run directory does not exist')
    print(json.dumps(inspect_run(args.run_dir, limit=args.limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
