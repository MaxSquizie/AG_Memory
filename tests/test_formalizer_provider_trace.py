"""Runtime observations preserve provider/protocol effects and explain failures."""
from types import SimpleNamespace

import pytest

from ah.diagnostics import runtime_trace
from ah.formalizer.kernel import BoundedExecutor, ProbeLimits, interpret
from ah.formalizer.pipeline import t0
from ah.formalizer.provider_adapter import (
    BudgetExceeded, BudgetSnapshot, IntegrityError, ProviderAdapter, ProviderUnavailable,
)
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.selection_exchange import exchange
from ah.formalizer.selection_prompt import SelectionPrompt
from ah.formalizer.selection_protocol import DecisionSchema, ProtocolError, Relation
from ah.formalizer.selector_wire import build_selector_prompt
from ah.formalizer.state import Decision


def rows(path):
    return list(runtime_trace.read_events(path))


@pytest.fixture
def trace(tmp_path):
    path = tmp_path / 'runtime.tsv'
    with runtime_trace.RuntimeTrace(path) as writer, runtime_trace.use_trace(writer):
        yield path


def adapter(transport=lambda prompt: '1', **kwargs):
    return ProviderAdapter('fixture', frozenset({'select', 'propose_local'}),
        transport=transport, **kwargs)


def test_provider_payload_and_received_replay_keep_identity(trace):
    calls = []
    raw = ' ответ\tс переносом\n'
    prompt = SelectionPrompt('исходный\tтекст\nстрока',
        {'candidates': ['candidate'], 'labels': {'1': 'candidate'}})
    provider = adapter(lambda request: calls.append(request) or raw)
    assert provider.select(prompt, 'run:test', ordinal=1) == raw
    assert provider.select(prompt, 'run:test', ordinal=1) == raw
    assert calls == [prompt]
    observed = rows(trace)
    requests = [row for row in observed if row['event'] == 'provider_request']
    receipts = [row for row in observed if row['event'] == 'provider_receipt']
    assert len(requests) == len(receipts) == 2
    assert requests[0]['data']['prompt'] == prompt
    assert requests[0]['data']['selection_audit'] == prompt.selection_audit
    assert [row['status'] for row in receipts] == ['RECEIVED', 'REPLAYED_RECEIVED']
    assert {row['entity_id'] for row in receipts} == {'run:test:fixture:1:1'}
    assert all(row['run_id'] == 'run:test' for row in receipts)
    assert all(row['data']['raw_response'] == raw for row in receipts)
    assert all(row['status'] != 'RESOLVED' for row in observed)


def test_transport_failure_and_failed_replay_do_not_retry(trace):
    calls = []

    def fail(prompt):
        calls.append(prompt)
        raise OSError('provider offline')

    provider = adapter(fail)
    with pytest.raises(ProviderUnavailable):
        provider.select('task', 'run:failed', ordinal=1)
    with pytest.raises(ProviderUnavailable, match='provider offline'):
        provider.select('task', 'run:failed', ordinal=1)
    assert calls == ['task']
    observed = rows(trace)
    receipt = next(row for row in observed if row['status'] == 'REPLAYED_FAILED')
    assert receipt['entity_id'] == 'run:failed:fixture:1:1'
    assert receipt['reason'] == 'provider offline'
    failed = [row for row in observed if row['event'] == 'span_failed']
    assert len(failed) == 2
    assert all(row['status'] == 'UNAVAILABLE' for row in failed)
    assert provider._log.state('run:failed:fixture:1:1') == 'FAILED'


@pytest.mark.parametrize('operation,expected_exception,reason', [
    ('missing', ProviderUnavailable, 'PROVIDER_UNAVAILABLE'),
    ('propose_local', BudgetExceeded, 'PROPOSAL_BUDGET'),
    ('propose_lexical', BudgetExceeded, 'PROPOSAL_BUDGET'),
])
def test_pretransport_failures_are_terminal_without_wal(trace, operation, expected_exception, reason):
    provider = adapter()
    if operation == 'missing':
        provider.capabilities = frozenset()
        operation = 'select'
    with pytest.raises(expected_exception):
        getattr(provider, operation)('task', 'run:blocked')
    assert provider._log._calls == {}
    failure = next(row for row in rows(trace) if row['event'] == 'span_failed')
    assert failure['reason'] == reason
    assert failure['run_id'] == 'run:blocked'


def test_received_bytes_are_visible_before_token_overflow(trace):
    provider = adapter(lambda prompt: 'x' * 100,
        budget=BudgetSnapshot(token_limit=10))
    with pytest.raises(BudgetExceeded):
        provider.select('p', 'run:overflow')
    observed = rows(trace)
    received = next(row for row in observed if row['event'] == 'provider_receipt')
    failure = next(row for row in observed if row['event'] == 'span_failed')
    assert received['status'] == 'RECEIVED'
    assert int(received['sequence']) < int(failure['sequence'])
    assert failure['status'] == 'BLOCKED'
    assert failure['reason'] == 'COMPUTATION_LIMIT'
    assert provider._tokens_used == 25
    assert provider._log.state('run:overflow:fixture:1:1') == 'RECEIVED'
    with pytest.raises(BudgetExceeded):
        provider.select('next', 'run:overflow')
    assert len(provider._log._calls) == 1
    assert len([row for row in rows(trace) if row['event'] == 'provider_receipt']) == 1


def test_source_window_limit_retains_exact_window_and_received_charge(trace):
    provider = adapter(lambda prompt: 'x' * 80)
    provider.configure_probe_windows(('window:0', 'window:1'), 10)
    provider.enter_probe_window('window:1')
    with pytest.raises(BudgetExceeded):
        provider.select('p', 'run:window')
    rejection = next(row for row in rows(trace) if row['event'] == 'provider_budget_rejected')
    assert rejection['data']['budget_scope'] == 'SOURCE_WINDOW'
    assert rejection['data']['window_key'] == 'window:1'
    assert rejection['data']['window_token_limit'] == 10
    assert provider._window_tokens.used == {'window:0': 0, 'window:1': 20}


def test_replay_integrity_failure_is_not_a_transport_failure(trace):
    provider = adapter()
    provider.select('first', 'run:integrity', ordinal=1)
    with pytest.raises(IntegrityError, match='REPLAY_MISMATCH'):
        provider.select('changed', 'run:integrity', ordinal=1)
    failure = next(row for row in rows(trace) if row['event'] == 'span_failed')
    assert failure['status'] == 'REJECTED'
    assert failure['reason'] == 'REPLAY_MISMATCH'
    assert failure['data']['error_type'] == 'IntegrityError'
    assert len(provider._log._calls) == 1


def test_tracing_does_not_change_provider_replay_or_budget_effects(tmp_path):
    results = []
    for logged in (False, True):
        writer = runtime_trace.RuntimeTrace(tmp_path / 'parity.tsv') if logged else None
        provider = adapter(lambda prompt: 'answer', budget=BudgetSnapshot(token_limit=100))
        with runtime_trace.use_trace(writer):
            values = [provider.select('prompt', 'stable-run', ordinal=1) for _ in range(2)]
        record = dict(provider._log.lookup('stable-run', 1))
        record.pop('response_time_ms')
        results.append((values, provider._tokens_used, provider._ordinals, record))
        if writer:
            writer.close()
    assert results[0] == results[1]


def test_broken_observer_does_not_change_return_or_transport_error():
    class BrokenSink:
        enabled = True

        def emit(self, *args, **kwargs):
            raise OSError('cannot log')

    with runtime_trace.use_trace(BrokenSink()):
        provider = adapter()
        assert provider.select('task', 'run:observer') == '1'
        with pytest.raises(IntegrityError, match='REPLAY_MISMATCH'):
            provider.select('changed', 'run:observer', ordinal=1)
    assert provider._log.state('run:observer:fixture:1:1') == 'RECEIVED'


def test_interrupted_transport_retains_pending_receipt_and_original_exception(trace):
    interruption = KeyboardInterrupt('cancelled by host')

    def cancel(prompt):
        raise interruption

    provider = adapter(cancel)
    with pytest.raises(KeyboardInterrupt) as raised:
        provider.select('task', 'run:cancelled')
    assert raised.value is interruption
    assert provider._log.state('run:cancelled:fixture:1:1') == 'PENDING'
    failure = next(row for row in rows(trace) if row['event'] == 'span_failed')
    assert failure['data']['error_type'] == 'KeyboardInterrupt'
    assert not any(row['event'] == 'provider_receipt' for row in rows(trace))


def test_executor_records_prompt_before_standalone_call_and_budget_rejection(trace):
    calls = []

    class Executor:
        def select(self, prompt):
            # The exact input is already flushed if this executor hangs/crashes.
            assert any(row['event'] == 'executor_request' for row in rows(trace))
            calls.append(prompt)
            return 'standalone reply'

    bounded = BoundedExecutor(Executor(), ProbeLimits(max_calls=1))
    assert bounded.select('task') == 'standalone reply'
    with pytest.raises(BudgetExceeded):
        bounded.select('blocked')
    observed = rows(trace)
    assert calls == ['task']
    assert (bounded.calls, bounded.input_chars) == (1, 4)
    assert [row['data']['prompt'] for row in observed if row['event'] == 'executor_request'] == ['task', 'blocked']
    rejected = next(row for row in observed if row['event'] == 'executor_budget_rejected')
    assert rejected['data']['dimension'] == 'calls'
    assert rejected['data']['used'] == 2


def test_executor_and_provider_share_payload_without_duplicate_bytes(trace):
    selector = RealBackendSelector(SimpleNamespace(generate=lambda prompt, **kwargs: '1'))
    selector.start_run('real-interface')
    bounded = BoundedExecutor(selector, ProbeLimits())
    assert bounded.select('the actual prompt') == '1'
    observed = rows(trace)
    assert len([row for row in observed if row['data'].get('prompt') == 'the actual prompt']) == 1
    assert len([row for row in observed if row['data'].get('raw_response') == '1']) == 1
    provider_request = next(row for row in observed if row['event'] == 'provider_request')
    assert provider_request['data']['payload_source'] == 'EXECUTOR'
    executor_span = next(row for row in observed if row['event'] == 'span_started' and row['stage'] == 'EXECUTOR')
    provider_span = next(row for row in observed if row['event'] == 'span_started' and row['stage'] == 'PROVIDER')
    assert provider_span['parent_span_id'] == executor_span['span_id']
    assert provider_span['trace_id'] == executor_span['trace_id']


def test_nested_executors_record_same_payload_only_once(trace):
    executor = SimpleNamespace(select=lambda prompt: 'nested response')
    inner = BoundedExecutor(executor, ProbeLimits())
    outer = BoundedExecutor(inner, ProbeLimits())
    assert outer.select('nested prompt') == 'nested response'
    observed = rows(trace)
    assert sum(row['data'].get('prompt') == 'nested prompt' for row in observed) == 1
    assert sum(row['data'].get('raw_response') == 'nested response' for row in observed) == 1
    assert inner.calls == outer.calls == 1


@pytest.mark.parametrize('responses,expected', [
    (['not a reply', '1'], 'ONE_SELECTED'),
    (['0'], 'NONE_FIT'),
    (['?'], 'INSUFFICIENT_CONTEXT'),
])
def test_selection_protocol_records_repair_and_retains_valid_zero_unknown(trace, responses, expected):
    class Executor:
        selection_reply_format = 'SELECT_LABELS_V1'

        def __init__(self):
            self.replies = iter(responses)

        def select(self, prompt):
            return next(self.replies)

    selector = BoundedExecutor(Executor(), ProbeLimits())
    state = t0('source')
    decision = Decision('test_slot', 'test_decision', ('c0',))
    schema = DecisionSchema('test', {'c0': Relation('c0', 'meaning', 0, (), 'meaning')})
    prompt = build_selector_prompt(selector, slot_id=decision.slot_id,
        frame_id=decision.frame_id, context_span='source', mentions={},
        schema=schema, candidates=decision.candidates)
    reply = exchange(state, selector, decision, prompt, schema, decision.candidates, 8192)
    assert reply.outcome == expected
    observed = rows(trace)
    validated = next(row for row in observed if row['event'] == 'selection_protocol_validated')
    assert validated['status'] == 'VALID'
    assert validated['data']['selector_outcome'] == expected
    assert validated['data']['semantic_validation_pending'] is True
    assert decision.outcome is None
    repairs = [row for row in observed if row['event'] == 'selection_protocol_repair_requested']
    assert len(repairs) == len(responses) - 1
    assert selector.calls == len(responses)


def test_kernel_invalid_input_has_failure_span(trace):
    with pytest.raises(ValueError, match='INPUT_REJECTED'):
        interpret('text', executor=None, release=None, observation={})
    failure = next(row for row in rows(trace) if row['event'] == 'span_failed')
    assert failure['stage'] == 'KERNEL'
    assert failure['reason'] == 'INPUT_REJECTED'


def test_two_invalid_selection_replies_leave_no_semantic_selection(trace):
    class InvalidExecutor:
        selection_reply_format = 'SELECT_LABELS_V1'

        def select(self, prompt):
            return 'invalid reply'

    selector = BoundedExecutor(InvalidExecutor(), ProbeLimits())
    state = t0('source')
    decision = Decision('slot', 'decision', ('c0',))
    schema = DecisionSchema('test', {'c0': Relation('c0', 'meaning', 0, (), 'meaning')})
    prompt = build_selector_prompt(selector, slot_id=decision.slot_id,
        frame_id=decision.frame_id, context_span='source', mentions={},
        schema=schema, candidates=decision.candidates)
    with pytest.raises(ProtocolError):
        exchange(state, selector, decision, prompt, schema, decision.candidates, 8192)
    observed = rows(trace)
    rejections = [row for row in observed if row['event'] == 'selection_protocol_rejected']
    assert [row['data']['attempt'] for row in rejections] == [0, 1]
    assert not any(row['event'] == 'selection_protocol_validated' for row in observed)
    assert selector.calls == state.budget.llm_calls == 2
    assert decision.outcome is None and decision.selected == ()


def test_component_input_rejection_does_not_issue_a_provider_call(trace):
    from ah.formalizer.component_probe import _probe
    state = t0('source')
    result = _probe(state, None, SimpleNamespace(sha256='release'),
        'missing-input', 'predicate_value', [{'candidate_id': 'candidate', 'label': 'one'}],
        'source', (0, 6))
    assert result is None
    assert state.decisions['missing-input'].outcome == 'UNRESOLVED'
    observed = rows(trace)
    terminal = next(row for row in observed if row['event'] == 'span_finished' and row['stage'] == 'COMPONENT_PROBE')
    assert terminal['status'] == 'NO_SELECTION'
    assert 'PROBE_INPUT_INCOMPLETE' in terminal['reason']
    assert not any(row['event'] == 'provider_request' for row in observed)


@pytest.mark.parametrize('system,wire,audited,expected_tokens', [
    (None, 'SELECT_LABELS_V1', True, 32),
    ('Custom\tpolicy\nsecond line', 'SELECT_LABELS_V1', True, 32),
    (None, 'JSON_V1', True, 100),
    (None, 'SELECT_LABELS_V1', False, 100),
])
def test_backend_context_is_the_effective_generate_input_and_is_not_replayed(trace, system, wire, audited, expected_tokens):
    class Backend:
        model = 'effective-model'

        def __init__(self):
            self.calls = []

        def generate(self, prompt, **kwargs):
            context = next(row for row in rows(trace) if row['event'] == 'backend_request_context')
            # The exact effective settings are available before transport starts.
            assert context['data']['system'] == kwargs['system']
            assert context['data']['role'] == kwargs['role']
            assert context['data']['generation_settings'] == kwargs['override']
            self.calls.append((prompt, kwargs))
            return '1'

    backend = Backend()
    settings = {'temperature': 0.0, 'top_p': 0.7, 'max_new_tokens': 100, 'enable_thinking': False}
    selector = RealBackendSelector(backend, system=system, role='formalizer-test',
        generation_settings=settings, selection_reply_format=wire)
    selector.start_run('effective-context')
    prompt = SelectionPrompt('source', {'candidates': ['a', 'b']}) if audited else 'source'
    assert selector.select(prompt) == '1'
    selector.start_run('effective-context')
    assert selector.select(prompt) == '1'
    contexts = [row for row in rows(trace) if row['event'] == 'backend_request_context']
    assert len(contexts) == len(backend.calls) == 1
    context = contexts[0]
    assert context['data']['generation_settings']['max_new_tokens'] == expected_tokens
    assert context['data']['model_key'] == 'effective-model'
    assert context['data']['backend_type'] == 'Backend'
    assert context['entity_id'] == 'effective-context:Backend:1:1'
    assert 'prompt' not in context['data'] and 'raw_response' not in context['data']
    assert selector.generation_settings == settings
    if system is None and audited and wire == 'SELECT_LABELS_V1':
        assert backend.calls[0][1]['system'] != selector.system
    else:
        assert backend.calls[0][1]['system'] == selector.system


def test_unprintable_integrity_error_keeps_exception_identity_with_and_without_logging(trace):
    class UnprintableIntegrityError(IntegrityError):
        def __str__(self):
            raise RuntimeError('string conversion failed')

    error = UnprintableIntegrityError()

    def fail_lookup(*args):
        raise error

    provider = adapter()
    provider._log.lookup = fail_lookup
    with runtime_trace.use_trace(None):
        with pytest.raises(UnprintableIntegrityError) as unlogged:
            provider.select('task', 'unprintable')
    with pytest.raises(UnprintableIntegrityError) as logged:
        provider.select('task', 'unprintable')
    assert unlogged.value is logged.value is error
    failure = next(row for row in rows(trace) if row['event'] == 'span_failed')
    assert failure['status'] == 'REJECTED'
    assert 'unprintable' in failure['reason']


def test_embedding_batch_cache_and_ranking_observations_preserve_order(trace, tmp_path):
    from ah.formalizer.lexical_embedding import order
    from test_lexical_embedding_order import fixture as make_fixture
    state, selector, release, frame, options, client = make_fixture(tmp_path / 'logged')
    baseline = make_fixture(tmp_path / 'baseline')
    with runtime_trace.use_trace(None):
        expected = order(*baseline[:5], 'source')
    actual = order(state, selector, release, frame, options, 'source')
    assert actual == expected == [options[1], options[0], options[2]]
    assert state.syntax_trace[-1] == baseline[0].syntax_trace[-1]
    selector.run_id = 'new-run-with-warm-cache'
    assert order(state, selector, release, frame, options, 'source') == expected
    observed = rows(trace)
    requests = [row for row in observed if row['event'] == 'embedding_request']
    assert [tuple(row['data']['texts']) for row in requests] == client.calls
    assert len(requests) == 1
    caches = [row for row in observed if row['event'] == 'embedding_cache_lookup']
    assert [row['status'] for row in caches] == ['MISS', 'HIT']
    assert caches[1]['data']['hit_texts'] == list(client.calls[0])
    response = next(row for row in observed if row['event'] == 'embedding_response')
    assert response['status'] == 'RECEIVED'
    assert response['data']['dimensions'] == [2, 2, 2]
    assert response['data']['validation_pending'] is True
    assert response['data']['raw_vectors_recorded'] is False
    ranked = [row for row in observed if row['stage'] == 'LEXICAL_EMBEDDING_RANK'
              and row['event'] == 'span_finished']
    assert len(ranked) == 2
    assert all(row['status'] == 'RANKED' for row in ranked)
    assert all(row['data']['scores'] == {'a': 0.0, 'b': 1.0} for row in ranked)
    assert all(row['data']['automatic_selection'] is False for row in ranked)


def test_embedding_replay_reads_scores_without_batch_or_cache_activity(trace, tmp_path):
    from ah.formalizer.lexical_embedding import LexicalEmbeddingRanker, order
    from test_lexical_embedding_order import fixture as make_fixture
    state, selector, release, frame, options, client = make_fixture(tmp_path)
    expected = order(state, selector, release, frame, options, 'source')

    class Offline:
        def embed(self, texts):
            raise AssertionError('network on replay')

    selector.lexical_ranker = LexicalEmbeddingRanker(Offline(), 'test-model')
    assert order(state, selector, release, frame, options, 'source') == expected
    observed = rows(trace)
    assert len([row for row in observed if row['event'] == 'embedding_request']) == 1
    assert len([row for row in observed if row['event'] == 'embedding_cache_lookup']) == 1
    assert any(row['event'] == 'provider_receipt' and row['status'] == 'REPLAYED_RECEIVED' for row in observed)
    assert not selector.lexical_ranker.cache


@pytest.mark.parametrize('failure,reason', [
    ('transport', 'embedding server unavailable'),
    ('count', 'embedding count mismatch'),
    ('dimension', 'embedding dimension mismatch'),
    ('value', 'invalid embedding values'),
])
def test_embedding_failures_are_observed_without_changing_fallback(trace, tmp_path, failure, reason):
    from ah.formalizer.lexical_embedding import order
    from test_lexical_embedding_order import fixture as make_fixture
    state, selector, release, frame, options, client = make_fixture(tmp_path)

    def embed(texts):
        if failure == 'transport':
            raise OSError('embedding server unavailable')
        if failure == 'count':
            return [[1, 0]]
        if failure == 'dimension':
            return [[1, 0], [1], [0, 1]]
        return [[True, 0] for _ in texts]

    client.embed = embed
    assert order(state, selector, release, frame, options, 'source') is options
    assert state.syntax_trace[-1]['status'] == 'UNAVAILABLE'
    assert not selector.lexical_ranker.cache
    observed = rows(trace)
    assert any(row['event'] == 'span_failed' and reason in row['reason'] for row in observed)
    final = next(row for row in observed if row['event'] == 'embedding_order_result')
    assert final['status'] == 'UNAVAILABLE'
    assert final['data']['ordered_candidates'] == ['a', 'b', 'open']
    assert final['data']['probe_required'] is True


def test_embedding_skip_does_not_read_unneeded_frame_or_make_request(trace, tmp_path):
    from ah.formalizer.lexical_embedding import order
    from test_lexical_embedding_order import fixture as make_fixture
    options = [{'candidate_id': 'unchanged'}]
    assert order(None, object(), None, None, options, None) is options
    state, selector, release, frame, options, client = make_fixture(tmp_path)
    frame.semantic['candidate_specs']['b']['sense_id'] = 'a'
    assert order(state, selector, release, frame, options, 'source') is options
    observed = rows(trace)
    assert not client.calls
    assert not any(row['event'] == 'embedding_request' for row in observed)
    assert any(row['reason'] == 'RANKER_NOT_CONFIGURED' for row in observed)
    assert any(row['reason'] == 'ONE_KNOWN_SENSE_NO_ORDERING_GAIN' for row in observed)
