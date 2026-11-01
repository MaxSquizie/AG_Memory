"""TSV observes actual formalization, including discarded execution state."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from threading import Barrier
from types import SimpleNamespace

import pytest

from ah.diagnostics import runtime_trace as trace
from ah.formalizer import runtime_tracing as tracing
from ah.formalizer.pipeline import t0
from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.formalizer.state import Decision
from ah.formalizer.telemetry import observe
from ah.formalizer.v7_pipeline import interpret_full
from tools.formalizer_v7_test_support import native_fixture, NativeSelector, FixtureMorph


TEXT = 'У Ивана есть книга.'


def rows(path):
    return list(trace.read_events(path))


def invoke(native, **kwargs):
    store, binding, release = native
    return interpret_full(TEXT, None, NativeSelector(), store, binding,
        release=release, morph=FixtureMorph(), run_id='runtime-test',
        raw_input={'source_id': 'runtime-test'}, **kwargs)


def assert_spans(observed):
    starts = [row for row in observed if row['event'] == 'span_started']
    ends = [row for row in observed if row['event'] in {'span_finished', 'span_failed'}]
    assert Counter(row['span_id'] for row in starts) == Counter(row['span_id'] for row in ends)
    by_id = {row['span_id']: row for row in starts}
    for row in starts:
        if row['parent_span_id']:
            parent = by_id[row['parent_span_id']]
            assert parent['trace_id'] == row['trace_id']
            assert int(parent['sequence']) < int(row['sequence'])
    assert not [row for row in observed if row['event'] == 'trace_capture_failed']


def test_native_logging_preserves_complete_ir_plan_hash_and_store(tmp_path):
    results = []
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer:
        for sink, directory in ((None, 'silent'), (writer, 'observed')):
            native = native_fixture(tmp_path / directory / 'journal')
            with trace.use_trace(sink):
                state, report = invoke(native)
            results.append((trace.encode_json(state), asdict(report), native[0].ledger.data))
    assert results[0] == results[1]
    assert results[1][1]['applied']
    observed = rows(path)
    assert_spans(observed)
    assert len({row['trace_id'] for row in observed}) == 1
    phases = {row['stage'] for row in observed if row['event'] == 'span_finished'}
    assert phases >= {'INPUT_VALIDATION', 'RUN_BINDING', 'T0_T1', 'T2_REGIONS',
                      'CONTEXT', 'T3_CANDIDATES', 'T4_RESOLUTION', 'T5_PLAN', 'T6_ADMISSION', 'T6_TRANSACTION'}
    assert any(row['event'] == 'decision_updated' and row['status'] == 'RESOLVED' for row in observed)
    assert any(row['event'] == 'plan_built' and row['data']['operations'] for row in observed)
    assert any(row['event'] == 'syntax_trace' for row in observed)
    final = observed[-1]
    assert final['stage'] == 'INTERPRETATION' and final['status'] == 'APPLIED'
    assert final['run_id'] == 'runtime-test'
    assert final['observation_id'] == results[1][1]['observation_id']


def test_repeated_durable_run_has_distinct_trace_identity_and_same_batch(tmp_path):
    native = native_fixture(tmp_path / 'journal')
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        first = invoke(native)[1]
        again = invoke(native)[1]
    assert first.applied and not again.applied and first.batch_hash == again.batch_hash
    observed = rows(path)
    starts = [row for row in observed if row['stage'] == 'INTERPRETATION' and row['event'] == 'span_started']
    assert len(starts) == 2 and starts[0]['trace_id'] != starts[1]['trace_id']
    assert {row['run_id'] for row in starts} == {'runtime-test'}
    assert [row['data']['replay'] for row in observed if row['event'] == 'run_binding_input'] == [False, True]
    assert_spans(observed)


def test_nonexception_refusal_keeps_reason_and_requested_version(tmp_path):
    native = native_fixture(tmp_path / 'journal')
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        state, report = interpret_full(TEXT, None, NativeSelector(), native[0], native[1],
            release=None, run_id='missing', observation_id='known', version=3)
    assert report.t5_eligibility == 'RESOURCE_MISSING' and not report.applied
    assert state.interpretation_version == 1  # Observe the existing placeholder without repairing it.
    observed = rows(path)
    diagnostic = next(row for row in observed if row['event'] == 'diagnostic')
    assert diagnostic['interpretation_version'] == '3'
    assert diagnostic['observation_id'] == 'known'
    assert observed[-1]['status'] == 'RESOURCE_MISSING'
    assert observed[-1]['interpretation_version'] == '3'
    assert_spans(observed)


def test_input_rejection_before_binding_has_terminal_error(tmp_path):
    path = tmp_path / 'runtime.tsv'
    native = native_fixture(tmp_path / 'journal')
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        with pytest.raises(ValueError, match='INPUT_REJECTED'):
            interpret_full(42, None, None, native[0], native[1])
    observed = rows(path)
    assert observed[-1]['event'] == 'span_failed'
    assert observed[-1]['stage'] == 'INTERPRETATION'
    assert 'INPUT_REJECTED' in observed[-1]['reason']
    assert not native[0].ledger.f_visible()
    assert_spans(observed)


def test_nested_document_observer_keeps_tsv_and_progress(tmp_path):
    from test_document_reading import services
    from ah.documents.reading import read_document
    service, _ = services(tmp_path / 'observed')
    source = tmp_path / 'source.txt'
    source.write_text(TEXT, encoding='utf-8')
    path = tmp_path / 'runtime.tsv'
    progress = []
    unobserved, _ = services(tmp_path / 'silent')
    with trace.use_trace(None):
        baseline = read_document(unobserved, source, tmp_path / 'baseline')
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer), observe(lambda event: None):
        report = read_document(service, source, tmp_path / 'report', progress=progress.append)
    assert (report['status'], report.get('error')) == (baseline['status'], baseline.get('error'))
    assert any(event['event'] == 'stage' and event['stage'] == 'T2_REGIONS' for event in progress)
    observed = rows(path)
    assert any(row['event'] == 'stage' and row['stage'] == 'T2_REGIONS' for row in observed)
    assert any(row['stage'] == 'HOST_INTERPRET' and row['event'] in {'span_finished', 'span_failed'} for row in observed)
    assert_spans(observed)


def test_projection_failure_does_not_relabel_committed_transaction(tmp_path, monkeypatch):
    store, binding, release = native_fixture(tmp_path / 'journal')
    adapter = FormalizerAdapter(NativeSelector(), FixtureMorph(), store=store, binding=binding, release=release)
    def fail(*args):
        raise LookupError('projection failed after commit')
    monkeypatch.setattr(adapter, '_receipt', fail)
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        with pytest.raises(LookupError, match='after commit'):
            adapter.interpret(TEXT, raw_input={'source_id': 'postcommit'})
    assert store.ledger.f_visible()
    observed = rows(path)
    transaction = next(row for row in observed if row['stage'] == 'T6_TRANSACTION' and row['event'] == 'span_finished')
    assert transaction['status'] == 'APPLIED'
    assert observed[-1]['stage'] == 'HOST_INTERPRET' and observed[-1]['event'] == 'span_failed'
    assert observed[-1]['run_id'] == transaction['run_id']
    assert observed[-1]['observation_id'] == transaction['observation_id']
    assert_spans(observed)


def test_failing_sink_and_progress_observer_preserve_commit(tmp_path):
    class BrokenWriter:
        enabled = True
        def emit(self, *args, **kwargs):
            raise OSError('unwritable')
    native = native_fixture(tmp_path / 'journal')
    def broken_progress(event):
        raise ValueError('broken observer')
    with trace.use_trace(BrokenWriter()), observe(broken_progress):
        _, report = invoke(native)
    assert report.applied and native[0].ledger.f_visible()


def test_private_execution_retains_rejection_without_replaying_inherited_history(tmp_path):
    from ah.formalizer.composition_session import session, CompositionSession, activate
    from ah.formalizer.structural_conditions import ConditionalHypothesis
    release = SimpleNamespace(sha256='release', entries=lambda name: [])

    @tracing.traced('PRIVATE_BRANCH_TEST')
    def execute():
        parent = t0('Иван')
        parent.source_uid = 'branch-source'
        tracing.watch_state(parent)
        parent.syntax_trace.append({'kind': 'INHERITED'})
        tracing.checkpoint(parent)
        with session(parent, release):
            child = deepcopy(parent)
            runtime = CompositionSession(child, release)
            condition = ConditionalHypothesis({}, 'hypothesis', {'label': 'one branch'}, {})
            with activate(runtime), tracing.condition_scope(child, condition):
                child.syntax_trace.append({'kind': 'PRIVATE_REJECTION', 'reason': 'CONSTRAINT'})
                child.reject('private-candidate', 'T2', 'CONSTRAINT')
                child.decisions['private'] = Decision('slot', 'frame', ('candidate',), outcome='UNRESOLVED')
            # A proof overlay can inspect/mutate its own diagnostic copy but is not execution.
            overlay = deepcopy(parent)
            overlay.diag('READ_ONLY_VIEW', 'not a new execution')
        assert not parent.rejections and not parent.decisions
        return parent

    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        execute()
    observed = rows(path)
    fork = next(row for row in observed if row['event'] == 'state_fork')
    child_ref = fork['data']['state_ref']
    assert fork['data']['parent_state_ref']
    inherited = [row for row in observed if row['event'] == 'syntax_trace' and row['data']['record']['kind'] == 'INHERITED']
    assert len(inherited) == 1
    private = next(row for row in observed if row['event'] == 'candidate_rejected')
    assert private['data']['state_ref'] == child_ref
    assert private['data']['condition_ref']
    assert private['data']['hypothesis_ref'] == 'hypothesis'
    assert any(row['event'] == 'decision_updated' and row['entity_id'] == 'private' for row in observed)
    assert not [row for row in observed if row['event'] == 'diagnostic' and row['reason'] == 'READ_ONLY_VIEW']
    assert_spans(observed)


def test_trace_restoration_is_marked_and_new_decision_is_not_lost(tmp_path):
    @tracing.traced('RESTORATION_TEST')
    def execute():
        state = t0('text')
        tracing.watch_state(state)
        state.syntax_trace.append({'kind': 'BEFORE'})
        state.diag('OLD', 'retirable')
        state.diagnostics[:] = []
        state.diag('NEW', 'same list length, new diagnostic')
        state.syntax_trace = [{'kind': 'RESTORED'}]
        tracing.checkpoint(state)
        state.syntax_trace.append({'kind': 'AFTER'})
        return state
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        execute()
    observed = rows(path)
    diagnostics = {row['data']['record']['code'] for row in observed if row['event'] == 'diagnostic'}
    assert diagnostics == {'OLD', 'NEW'}
    restored = next(row for row in observed if row['event'] == 'syntax_trace' and row['data']['record']['kind'] == 'RESTORED')
    assert restored['data']['capture'] == 'restored_snapshot'
    assert any(row['event'] == 'syntax_trace' and row['data']['record']['kind'] == 'AFTER' for row in observed)


def test_exception_flushes_last_stage_diagnostics_and_preserves_exception(tmp_path):
    error = RuntimeError('original failure')
    @tracing.traced('FAILED_BRANCH')
    def execute():
        state = t0('text')
        tracing.watch_state(state)
        with tracing.phase('T2', state):
            state.syntax_trace.append({'kind': 'LAST_OPERATION'})
            raise error
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        with pytest.raises(RuntimeError) as caught:
            execute()
    assert caught.value is error
    observed = rows(path)
    last = next(row for row in observed if row['event'] == 'syntax_trace')
    failed = next(row for row in observed if row['event'] == 'span_failed' and row['stage'] == 'T2')
    assert int(last['sequence']) < int(failed['sequence'])
    assert_spans(observed)


def test_unprintable_exception_is_not_replaced_by_state_observer(tmp_path):
    class OriginalError(Exception):
        def __str__(self):
            raise ValueError('error renderer failed')
    original = OriginalError()
    @tracing.traced('UNPRINTABLE_ERROR')
    def execute():
        state = t0('text')
        tracing.watch_state(state)
        with tracing.executing_state(state):
            raise original
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        with pytest.raises(OriginalError) as failure:
            execute()
    assert failure.value is original
    observed = rows(path)
    assert observed[-1]['data']['error_type'] == 'OriginalError'
    assert 'unprintable' in observed[-1]['reason']
    assert_spans(observed)


def test_trace_reader_handles_large_json_and_reports_truncated_rows(tmp_path):
    path = tmp_path / 'runtime.tsv'
    payload = 'много текста\t\n' * 30000
    with trace.RuntimeTrace(path) as writer:
        writer.emit('large', reason='literal\\n\tnewline\n', payload=payload)
    event = next(trace.read_events(path))
    assert event['data']['payload'] == payload
    assert event['reason'] == 'literal\\n\tnewline\n'
    truncated = tmp_path / 'truncated.tsv'
    truncated.write_bytes(path.read_bytes()[:-3])
    with pytest.raises(ValueError, match='ROW_INCOMPLETE'):
        list(trace.read_events(truncated))


def test_concurrent_formalizations_keep_run_and_observation_context(tmp_path):
    barrier = Barrier(2)
    class ConcurrentSelector(NativeSelector):
        def __init__(self):
            super().__init__()
            self.first = True
        def select(self, prompt):
            if self.first:
                self.first = False
                barrier.wait(timeout=10)
            return super().select(prompt)
    path = tmp_path / 'runtime.tsv'
    native = [native_fixture(tmp_path / str(index) / 'journal') for index in range(2)]
    with trace.RuntimeTrace(path) as writer:
        def run(index):
            store, binding, release = native[index]
            with trace.use_trace(writer):
                return interpret_full(TEXT, None, ConcurrentSelector(), store, binding,
                    release=release, morph=FixtureMorph(), run_id=f'run:{index}',
                    observation_id=f'observation:{index}')[1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            reports = list(pool.map(run, range(2)))
    assert all(report.applied for report in reports)
    observed = rows(path)
    for index in range(2):
        own = [row for row in observed if row['observation_id'] == f'observation:{index}']
        assert own and {row['run_id'] for row in own} == {f'run:{index}'}
        assert len({row['trace_id'] for row in own}) == 1
    assert_spans(observed)


def test_native_conditional_branches_are_observed_in_real_pipeline(tmp_path, monkeypatch):
    from test_structural_open_forest import native
    from test_structural_conditional_shells import boundaries, shells
    def reject(slot, prompt):
        return '0' if slot == 'structural_partition' else boundaries(slot, prompt)
    path = tmp_path / 'runtime.tsv'
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        state, result, _ = native(tmp_path, monkeypatch, ('AND', 'OR'), reject)
    assert not result['assertions']['ah']
    assert all(shell['status'] == 'OPEN' for shell in shells(state))
    observed = rows(path)
    conditions = {row['data']['condition_ref'] for row in observed if row['event'] == 'condition_entered'}
    assert len(conditions) >= 2
    rejections = [row for row in observed if row['event'] == 'syntax_trace'
                  and row['data']['record'].get('category') == 'PARTITION_REJECTED']
    assert rejections
    assert all(row['data'].get('condition_ref') in conditions for row in rejections)
    assert_spans(observed)
