"""Inspect a real source through the production formalizer, with no gold corpus.

Artifacts are observations of this run, not replay authority or a correctness
oracle. Canonical recovery remains owned by the native journals/run binding.
"""
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
from time import monotonic

from ah.formalizer.telemetry import observe


def _json(value):
    if is_dataclass(value): return _json(asdict(value))
    if isinstance(value, Enum): return value.value
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, Path): return str(value)
    if isinstance(value, dict): return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_json(v) for v in value]
    if isinstance(value, (set, frozenset)): return sorted((_json(v) for v in value), key=str)
    return value


def _dump(path, value):
    path.write_text(json.dumps(_json(value), ensure_ascii=False, indent=2), encoding='utf-8')


def summarize_snapshot(snapshot):
    """Report actual anchors/decisions, never label parsed characters as truth."""
    state = snapshot.get('state', {})
    forest = state.get('region_forest') or {}
    evidence = state.get('evidence', [])
    frames = state.get('frames', [])
    anchored = {ref for f in frames for ref in
                [f['predicate_token_ref'], *f.get('argument_token_refs', [])]}
    # Expose unanchored tokens, including punctuation; this is deliberately not
    # called semantic coverage (operator anchors and unresolved scopes differ).
    unanchored = [{'token_ref': e['token_id'], 'range': [e['start'], e['end']], 'text': e['span']}
                  for e in evidence if e['token_id'] not in anchored]
    decisions = state.get('decisions', {})
    receipt = snapshot.get('commit_receipt', {})
    return {
        'observation_id': receipt.get('observation_id'),
        'terminal': receipt.get('terminal'),
        'committed_fragments': receipt.get('committed_fragments', []),
        'node_refs': receipt.get('node_refs', []),
        'regions_by_kind': dict(Counter(r['kind'] for r in forest.get('regions', []))),
        'frames': len(frames), 'tokens': len(evidence),
        'decisions_by_outcome': dict(Counter(d.get('outcome', 'PENDING') for d in decisions.values())),
        'unresolved_decisions': {key: d for key, d in decisions.items() if d.get('outcome') != 'RESOLVED'},
        'diagnostics': state.get('diagnostics', []),
        'unanchored_tokens': unanchored,
        'context_reads': len(state.get('context_reads', [])),
        'semantic_correctness': 'NOT_EVALUATED',
    }


def read_document(services, path, output_dir, *, progress=None, source_timestamp=None):
    """Run a single arbitrary file on the configured live AH and local provider.

    Every attempt needs a new artifact directory. Repeating an unchanged source
    uses native replay; no previous report/expected result is fed to the model.
    """
    source = Path(path)
    raw = source.read_bytes()
    processor = services.document_processor()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    saved_source = out / ('source' + source.suffix)
    saved_source.write_bytes(raw)
    text = processor.load_text(saved_source)
    with (out / 'source.txt.decoded').open('w', encoding='utf-8', newline='') as stream:
        stream.write(text)
    adapter = getattr(getattr(services, 'perception', None), '_formalizer', None)
    report = {'schema': 'document-reading-1', 'source_path': str(source.resolve()),
              'source_sha256': hashlib.sha256(raw).hexdigest(),
              'decoded_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
              'source_chars': len(text), 'output_dir': str(out.resolve()),
              'boundary_policy': 'WHOLE_SOURCE', 'status': 'RUNNING',
              'semantic_correctness': 'NOT_EVALUATED',
              'resource_snapshot': getattr(getattr(adapter, '_release', None), 'sha256', None),
              'structural_contract': getattr(adapter, '_structure_mode', None)}
    _dump(out / 'report.json', report)
    counts = Counter()
    stage_times = Counter()
    stage, since = 'START', monotonic()
    started = since
    event_io_errors = []
    with (out / 'progress.jsonl').open('w', encoding='utf-8') as events:
        def callback(event):
            nonlocal stage, since
            now = monotonic()
            counts[event['event']] += 1
            if event['event'] == 'stage':
                stage_times[stage] += now - since
                stage, since = event['stage'], now
            payload = {**event, 'elapsed_seconds': now-started, 'stage': stage,
                       'probes_started': counts['probe_started'],
                       'probes_finished': counts['probe_finished'],
                       'probes_replayed': counts['probe_replayed']}
            try:
                events.write(json.dumps(_json(payload), ensure_ascii=False) + '\n')
                events.flush()
            except OSError as exc:
                if not event_io_errors: event_io_errors.append(str(exc))
            if progress is not None:
                try: progress(payload)
                except Exception: pass

        snapshot = None
        try:
            if adapter is None or adapter._structure_mode != 'region_probes':
                raise ValueError('DOCUMENT_REQUIRES_REGION_PROBES: no legacy graph proposer fallback')
            with services.operation_lock, observe(callback):
                before = adapter.diagnostic_sequence()
                try:
                    ingestion = processor.ingest_text(text, title=source.stem, source_timestamp=source_timestamp)
                finally:
                    if adapter.diagnostic_sequence() != before:
                        snapshot = adapter.diagnostic_snapshot()
            report.update(status='EXECUTED', source_ref=ingestion.source_ref,
                          observations=len(ingestion.chunks))
        except Exception as exc:
            # A typed failure can already have a native diagnostic snapshot.
            # This report never promises rollback of canonical writes.
            report.update(status='STOPPED', error={'type': type(exc).__name__, 'message': str(exc)})
        finally:
            stage_times[stage] += monotonic() - since
            report.update(elapsed_seconds=monotonic()-started, stages_seconds=dict(stage_times),
                          events=dict(counts), artifact_errors=event_io_errors)
            if snapshot is not None:
                _dump(out / 'interpretation.json', snapshot)
                state = snapshot.get('state', {})
                _dump(out / 'regions.json', state.get('region_forest') or {})
                report['interpretation'] = summarize_snapshot(snapshot)
            _dump(out / 'report.json', report)
    return report
