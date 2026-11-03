#!/usr/bin/env python3
"""Export blind probe annotations and score them against the exact recorded replies.

This is an offline evaluator. It neither calls a model nor inserts invented
partitions into a production interpretation. Gold is supplied by a reviewer.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tools.audit_formalizer_runtime import load_runtime, collect_exchanges, digest, ratio, unscored_boundaries
from ah.diagnostics.probe_catalog import evidence_clipped
from ah.formalizer.selection_labels import validate_selection_label_response, PROTOCOL_VERSION
from ah.formalizer.selection_protocol import DecisionSchema, Relation, ProtocolError


def eligible(item):
    audit = item['selection_audit']
    if item['operation'] != 'select' or not isinstance(item['prompt'], str):
        return False
    if not isinstance(audit, dict) or audit.get('protocol') != PROTOCOL_VERSION or evidence_clipped(audit):
        return False
    context = item['backend_input_context']
    if not context or evidence_clipped(context) or not item.get('params_hash'):
        return False
    if any(not isinstance(c.get('generation_settings'), dict) or not isinstance(c.get('role'), str)
           or not isinstance(c.get('system'), (str, type(None))) for c in context):
        return False
    ids = audit.get('candidates')
    return (isinstance(ids, list) and all(isinstance(v, str) and v for v in ids)
            and len(ids) == len(set(ids)))


def export_annotations(loaded):
    exchanges = collect_exchanges(loaded['rows'])
    samples = []
    for item in exchanges:
        if not eligible(item):
            continue
        sample = {key: item[key] for key in ('sample_id', 'event_address', 'payload_sha256',
            'prompt_sha256', 'prompt', 'selection_audit', 'slot', 'pipeline_stage',
            'case_id', 'decision_ref', 'state_ref', 'condition_ref', 'model_key', 'params_hash',
            'backend_input_context', 'backend_context_source', 'backend_context_sha256',
            'sample_kind', 'protocol_attempt')}
        sample['annotation'] = None
        samples.append(sample)
    return {'schema_version': 'probe-controls-1', 'source_trace_sha256': loaded['source_sha256'],
        'corpus_kind': 'ANNOTATED_RUNTIME', 'g5_holdout_claim': False,
        'provenance': 'Fill in who selected and independently annotated these probes, and how.',
        'samples': samples, 'omitted_unscorable_provider_invocations': len(exchanges) - len(samples),
        'unscored_execution_boundaries': unscored_boundaries(loaded['rows'], exchanges),
        'instructions': 'Annotate each included prompt independently. Do not infer gold from the recorded '
        'model response or the final case status. Set annotation to {reviewer, rationale, '
        'expected_outcome, expected_selected}; outcomes are ONE_SELECTED, MULTIPLE_ADMISSIBLE, '
        'NONE_FIT, INSUFFICIENT_CONTEXT. Selected values are candidate IDs in selection_audit order. '
        'Remove unreviewed samples before scoring. Engineered negative proposals require their own '
        'separate evaluation execution and trace; changing this exported prompt breaks its binding.'}


def validated_annotation(sample, item):
    if not eligible(item):
        raise ValueError('sample has incomplete prompt or candidate evidence')
    for field in ('event_address', 'payload_sha256', 'prompt_sha256', 'prompt', 'selection_audit',
                  'backend_input_context', 'backend_context_source', 'backend_context_sha256',
                  'model_key', 'params_hash'):
        if sample.get(field) != item[field]:
            raise ValueError('annotation binding mismatch: ' + field)
    annotation = sample.get('annotation')
    if not isinstance(annotation, dict):
        raise ValueError('sample has not been independently annotated: ' + item['sample_id'])
    for field in ('reviewer', 'rationale'):
        if not isinstance(annotation.get(field), str) or not annotation[field].strip():
            raise ValueError('annotation requires ' + field)
    outcome, selected = annotation.get('expected_outcome'), annotation.get('expected_selected')
    if outcome not in {'ONE_SELECTED', 'MULTIPLE_ADMISSIBLE', 'NONE_FIT', 'INSUFFICIENT_CONTEXT'}:
        raise ValueError('unknown expected outcome')
    if not isinstance(selected, list) or any(not isinstance(v, str) for v in selected) or len(selected) != len(set(selected)):
        raise ValueError('expected selection must be a list of distinct candidate IDs')
    if not set(selected) <= set(item['selection_audit']['candidates']):
        raise ValueError('expected selection includes an unknown candidate')
    cardinality = len(selected)
    if ((outcome == 'ONE_SELECTED' and cardinality != 1)
            or (outcome == 'MULTIPLE_ADMISSIBLE' and cardinality < 2)
            or (outcome in {'NONE_FIT', 'INSUFFICIENT_CONTEXT'} and cardinality != 0)):
        raise ValueError('expected outcome/cardinality mismatch')
    return annotation


def score_annotations(loaded, annotations):
    if annotations.get('schema_version') != 'probe-controls-1':
        raise ValueError('unsupported control schema')
    if annotations.get('source_trace_sha256') != loaded['source_sha256']:
        raise ValueError('annotation source trace hash mismatch')
    if annotations.get('corpus_kind') not in {'ANNOTATED_RUNTIME', 'ENGINEERED_CONTROLS', 'SYNTHETIC_FIXTURE'}:
        raise ValueError('declare the actual control corpus kind')
    if not isinstance(annotations.get('provenance'), str) or not annotations['provenance'].strip():
        raise ValueError('control provenance is required')
    samples = annotations.get('samples')
    if not isinstance(samples, list) or not samples:
        raise ValueError('at least one independently annotated sample is required')
    exchanges = {item['sample_id']: item for item in collect_exchanges(loaded['rows'])}
    seen = set()
    results = []
    for sample in samples:
        sample_id = sample.get('sample_id')
        if sample_id in seen:
            raise ValueError('duplicate annotated event')
        seen.add(sample_id)
        if sample_id not in exchanges or digest(sample.get('event_address')) != sample_id:
            raise ValueError('annotation references an unknown event')
        item = exchanges[sample_id]
        annotation = validated_annotation(sample, item)
        raw = item['raw_response']
        observed = item['classification']['outcome']
        selected = []
        if item['response_received']:
            ids = item['selection_audit']['candidates']
            schema = DecisionSchema(item['selection_audit'].get('schema', 'control-audit'),
                {cid: Relation(cid, cid, 0, (), cid) for cid in ids})
            try:
                reply = validate_selection_label_response(raw, schema, ids, allowed=frozenset(ids))
            except ProtocolError:
                observed = 'MALFORMED'
            else:
                observed, selected = reply.outcome, list(reply.selected)
        exact = (observed == annotation['expected_outcome']
                 and set(selected) == set(annotation['expected_selected']))
        expected = annotation['expected_outcome']
        results.append({'sample_id': sample_id, 'event_address': item['event_address'],
            'raw_slot': item['slot']['raw_slot'], 'sample_kind': item['sample_kind'],
            'model_key': item['model_key'], 'params_hash': item['params_hash'],
            'backend_context_sha256': item['backend_context_sha256'],
            'expected_outcome': expected, 'expected_selected': annotation['expected_selected'],
            'observed_outcome': observed, 'observed_selected': selected, 'exact': exact,
            'false_acceptance': expected == 'NONE_FIT' and observed in {'ONE_SELECTED', 'MULTIPLE_ADMISSIBLE'},
            'false_rejection': expected in {'ONE_SELECTED', 'MULTIPLE_ADMISSIBLE'} and observed == 'NONE_FIT',
            'abstained': observed == 'INSUFFICIENT_CONTEXT',
            'terminal_status': item['terminal_status'], 'blocked_after_receipt': item['blocked_after_receipt']})
    grouped = defaultdict(list)
    for row in results:
        grouped[(row['sample_kind'], row['raw_slot'], row['model_key'], row['params_hash'],
                 row['backend_context_sha256'])].append(row)
    metrics = []
    valid = {'ONE_SELECTED', 'MULTIPLE_ADMISSIBLE', 'NONE_FIT', 'INSUFFICIENT_CONTEXT'}
    decisive = {'ONE_SELECTED', 'MULTIPLE_ADMISSIBLE', 'NONE_FIT'}
    for (kind, slot, model, params, context_sha), group in sorted(grouped.items()):
        negatives = [r for r in group if r['expected_outcome'] == 'NONE_FIT']
        positives = [r for r in group if r['expected_outcome'] in {'ONE_SELECTED', 'MULTIPLE_ADMISSIBLE'}]
        metrics.append({'sample_kind': kind, 'raw_slot': slot, 'model_key': model,
            'params_hash': params, 'backend_context_sha256': context_sha, 'annotated_samples': len(group),
            'observed_outcomes': dict(Counter(r['observed_outcome'] for r in group)),
            'exact_all_annotations': ratio(sum(r['exact'] for r in group), len(group)),
            'exact_among_valid_replies': ratio(sum(r['exact'] for r in group), sum(r['observed_outcome'] in valid for r in group)),
            'negative_controls': len(negatives),
            'negative_abstentions': sum(r['abstained'] for r in negatives),
            'false_acceptance_among_decisive_negative_replies': ratio(sum(r['false_acceptance'] for r in negatives),
                sum(r['observed_outcome'] in decisive for r in negatives)),
            'positive_controls': len(positives),
            'positive_abstentions': sum(r['abstained'] for r in positives),
            'false_rejection_among_decisive_positive_replies': ratio(sum(r['false_rejection'] for r in positives),
                sum(r['observed_outcome'] in decisive for r in positives))})
    return {'schema_version': 'probe-control-score-1', 'source_trace_sha256': loaded['source_sha256'],
        'annotation_sha256': digest(annotations), 'corpus_kind': annotations['corpus_kind'],
        'provenance': annotations['provenance'], 'metrics': metrics, 'samples': results,
        'g5_holdout_claim': False, 'runtime_error_prevalence': 'NOT_ESTIMATED',
        'model_confidence': 'NOT_MEASURED',
        'note': 'INITIAL, FORMAT_REPAIR, REPLAY and UNSCOPED are separate strata. A negative-control '
                'abstention is not a correct rejection. No probability calibration is inferred. '
                'Engineered controls do not estimate natural runtime error prevalence.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['export', 'score'])
    parser.add_argument('runtime', type=Path)
    parser.add_argument('--annotations', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.mode == 'score' and args.annotations is None:
        parser.error('--annotations is required for score')
    if args.mode == 'export' and args.annotations is not None:
        parser.error('--annotations is only used for score')
    if args.out.exists():
        parser.error('output already exists')
    loaded = load_runtime(args.runtime)
    result = (export_annotations(loaded) if args.mode == 'export' else score_annotations(loaded,
              json.loads(args.annotations.read_text(encoding='utf-8'))))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
