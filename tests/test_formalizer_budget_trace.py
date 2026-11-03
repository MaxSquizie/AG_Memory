"""Independent accounting receipts describe existing charges, never reserve them."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from ah.diagnostics import runtime_trace
from ah.formalizer import budget_tracing, probe_windows
from ah.formalizer.kernel import BoundedExecutor, ProbeLimits
from ah.formalizer.provider_adapter import BudgetExceeded, BudgetSnapshot, ProviderAdapter, ProviderUnavailable
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.runtime_tracing import phase
from ah.formalizer.selection_exchange import exchange
from ah.formalizer.selection_protocol import DecisionSchema, Relation
from ah.formalizer.selector_wire import build_selector_prompt
from ah.formalizer.state import Budget, Decision, FormalizationState


@pytest.fixture
def trace(tmp_path):
    path = tmp_path / 'runtime.tsv'
    with runtime_trace.RuntimeTrace(path) as writer, runtime_trace.use_trace(writer):
        yield path


def events(path, event=None, level=None):
    return [row for row in runtime_trace.read_events(path)
            if (event is None or row['event'] == event)
            and (level is None or row['data'].get('budget_level') == level)]


def provider(transport=lambda prompt: '1', **kwargs):
    return ProviderAdapter('fixture', frozenset({'select', 'propose_local'}),
                           transport=transport, **kwargs)


def test_executor_effective_limits_are_visible_without_a_failure_or_start_run(trace):
    limits = ProbeLimits(max_calls=7, max_prompt_chars=333, max_input_chars=999,
                         max_elapsed_seconds=23.5)
    # An injected executor can be constructed before a writer is selected.
    with runtime_trace.use_trace(None):
        bounded = BoundedExecutor(SimpleNamespace(select=lambda prompt: '?'), limits)
    with phase('T2_REGIONS'):
        assert bounded.select('source') == '?'
    configured = events(trace, 'budget_configured', 'EXECUTOR')
    assert len(configured) == 1
    data = configured[0]['data']
    assert data['limits'] == asdict(limits)
    assert data['counters'] == {'calls': 0, 'input_chars': 0}
    assert data['pipeline_stage'] == 'T2_REGIONS'
    charged = events(trace, 'budget_charged', 'EXECUTOR')[0]
    assert charged['data']['before'] == {'calls': 0, 'input_chars': 0}
    assert charged['data']['delta'] == {'calls': 1, 'input_chars': 6}
    assert charged['data']['after'] == {'calls': 1, 'input_chars': 6}
    assert 'elapsed_seconds' not in charged['data']['delta']
    assert charged['data']['budget_ref'] == data['budget_ref']
    assert int(configured[0]['sequence']) < int(charged['sequence'])


@pytest.mark.parametrize('dimension,limits,prompt,clock', [
    ('prompt_chars', ProbeLimits(max_prompt_chars=2), 'long', (0.0, 0.1)),
    ('input_chars', ProbeLimits(max_input_chars=2), 'long', (0.0, 0.1)),
    ('elapsed_seconds', ProbeLimits(max_elapsed_seconds=2), 'ok', (0.0, 2.1)),
])
def test_executor_early_gate_records_all_limits_without_charging(trace, monkeypatch, dimension, limits, prompt, clock):
    from ah.formalizer import kernel
    samples = iter(clock)
    monkeypatch.setattr(kernel, 'monotonic', lambda: next(samples))
    calls = []
    bounded = BoundedExecutor(SimpleNamespace(select=lambda request: calls.append(request)), limits)
    with pytest.raises(BudgetExceeded):
        bounded.select(prompt)
    rejected = events(trace, 'executor_budget_rejected', 'EXECUTOR')[0]['data']
    assert rejected['dimension'] == dimension
    assert (bounded.calls, bounded.input_chars, calls) == (0, 0, [])
    assert events(trace, 'budget_charged', 'EXECUTOR') == []
    assert events(trace, 'budget_configured', 'EXECUTOR')[-1]['data']['limits'] == asdict(limits)


def test_nested_executors_have_separate_owners_and_input_size_contracts(trace):
    executor = SimpleNamespace(select=lambda prompt: '1', prompt_size=lambda prompt: len(prompt) + 11)
    inner = BoundedExecutor(executor, ProbeLimits(max_calls=2))
    outer = BoundedExecutor(inner, ProbeLimits(max_calls=3))
    assert outer.select('data') == '1'
    charges = [row['data'] for row in events(trace, 'budget_charged', 'EXECUTOR')]
    assert len(charges) == 2
    assert len({row['budget_ref'] for row in charges}) == 2
    assert all(row['delta'] == {'calls': 1, 'input_chars': 15} for row in charges)
    assert all(row['input_size_source'] == 'PROMPT_SIZE_HOOK' for row in charges)
    assert inner.calls == outer.calls == 1


def test_shared_budget_across_branch_states_charges_once_per_spend(trace):
    parent = FormalizationState('source', 1, 1, 'text', budget=Budget(llm_limit=3))
    child = deepcopy(parent)
    child.budget = parent.budget
    with phase('T2_REGIONS'):
        parent.budget.spend_llm()
        child.budget.spend_llm(failed=True)
    with phase('T4_RESOLUTION'):
        child.budget.spend_llm()
        assert parent.budget.llm_exhausted
    charges = [row['data'] for row in events(trace, 'budget_charged', 'STATE_CALLS')]
    assert len(charges) == 3
    assert len({row['budget_ref'] for row in charges}) == 1
    assert [row['before']['llm_calls'] for row in charges] == [0, 1, 2]
    assert [row['after']['llm_calls'] for row in charges] == [1, 2, 3]
    assert sum(row['delta']['llm_calls'] for row in charges) == parent.budget.llm_calls == 3
    assert sum(row['delta']['llm_failed'] for row in charges) == parent.budget.llm_failed == 1
    assert [row['pipeline_stage'] for row in charges] == ['T2_REGIONS', 'T2_REGIONS', 'T4_RESOLUTION']
    checked = events(trace, 'budget_checked', 'STATE_CALLS')[-1]
    assert checked['status'] == 'EXHAUSTED' and checked['data']['check_only'] is True
    assert checked['data']['limit'] == 3
    assert not any(name.startswith('_trace') or name.startswith('budget_ref') for name in asdict(parent.budget))


@pytest.mark.parametrize('calls_limit,tokens_limit,effective_tokens', [(2, 50, 24), (0, 0, 0)])
def test_source_window_configuration_reentry_and_cumulative_charges(trace, calls_limit, tokens_limit, effective_tokens):
    policy = {'version': 'SOURCE_WINDOW_V2', 'window_tokens': 16,
              'calls_per_window': calls_limit, 'tokens_per_window': tokens_limit}
    release = SimpleNamespace(sha256='released-fixture', entries=lambda kind: [{'probe_budget': policy}])
    state = FormalizationState('source', 1, 1, 'x ' * 34,
        evidence=[SimpleNamespace(start=i * 2) for i in range(34)],
        observation={'structural_contract': 'region_probes'})
    adapter = provider(budget=BudgetSnapshot(token_limit=24))
    probe_windows.configure(state, adapter, release)
    for stage, start in [('T2_REGIONS', 0), ('T2_REGIONS', 32), ('T4_RESOLUTION', 0)]:
        with phase(stage):
            probe_windows.enter(state, adapter, (start, start + 2))
            state.budget.spend_llm()
            assert adapter.select('twelve chars', 'window-run') == '1'
    assert state.budget.probe_window_starts == [0, 32, 64]
    assert state.budget.probe_scope_calls == {'0': 2, '1': 1}
    assert state.budget.llm_exhausted is (calls_limit != 0)
    configurations = [row['data'] for row in events(trace, 'budget_configured', 'STATE_CALLS')
                      if row['data']['scope'] == 'SOURCE_WINDOW']
    assert configurations[0]['source_policy'] == policy
    assert configurations[0]['source_window_unit'] == 'TOKEN_EVIDENCE_ITEMS'
    assert configurations[0]['limits']['calls_per_window'] == {'0': calls_limit, '1': calls_limit, '2': calls_limit}
    provider_config = events(trace, 'budget_configured', 'PROVIDER')[-1]['data']
    assert provider_config['limits']['token_limit'] == 24
    assert provider_config['limits']['tokens_per_window'] == {'0': effective_tokens, '1': effective_tokens, '2': effective_tokens}
    assert provider_config['requested_tokens_per_window'] == tokens_limit
    charges = [row['data'] for row in events(trace, 'budget_charged', 'PROVIDER')]
    assert [row['window_key'] for row in charges] == ['0', '1', '0']
    assert [row['before']['estimated_tokens'] for row in charges] == [0, 3, 6]
    assert [row['before']['window_estimated_tokens'] for row in charges] == [0, 0, 3]
    assert [row['after']['window_estimated_tokens'] for row in charges] == [3, 3, 6]
    assert all(row['delta'] == {'estimated_tokens': 3} for row in charges)
    assert charges[-1]['pipeline_stage'] == 'T4_RESOLUTION'
    entered = events(trace, 'budget_window_entered', 'STATE_CALLS')[-1]['data']
    assert entered['window_key'] == '0' and entered['window_used'] == 1
    assert entered['source_range'] == [0, 2]


def test_missing_window_is_a_check_and_rejected_spend_without_charge(trace):
    budget = Budget(probe_scope_limits={'0': 1})
    assert budget.llm_exhausted
    with pytest.raises(ValueError, match='PROBE_SCOPE_REQUIRED'):
        budget.spend_llm()
    assert budget.llm_calls == 0 and budget.probe_scope_calls == {}
    checked = events(trace, 'budget_checked', 'STATE_CALLS')[0]
    assert checked['reason'] == 'PROBE_SCOPE_REQUIRED' and checked['data']['check_only'] is True
    assert events(trace, 'state_budget_rejected', 'STATE_CALLS')[0]['reason'] == 'PROBE_SCOPE_REQUIRED'
    assert events(trace, 'budget_charged', 'STATE_CALLS') == []


@pytest.mark.parametrize('fails', [False, True])
def test_provider_live_and_replayed_accounting_share_owner_but_not_transport(trace, fails):
    physical_calls = []

    class Backend:
        def generate(self, prompt, **kwargs):
            physical_calls.append(prompt)
            if fails:
                raise OSError('offline')
            return 'reply'

    selector = RealBackendSelector(Backend(), system='system excluded from provider estimate',
        budget=BudgetSnapshot(token_limit=100))
    for repeat in range(2):
        selector.start_run('same-run')
        with phase('T4_RESOLUTION'):
            if fails:
                with pytest.raises(ProviderUnavailable):
                    selector.select('request')
            else:
                assert selector.select('request') == 'reply'
    charges = [row['data'] for row in events(trace, 'budget_charged', 'PROVIDER')]
    assert len(charges) == 2 and len(physical_calls) == 1
    assert [row['replay'] for row in charges] == [False, True]
    assert {row['exchange_outcome'] for row in charges} == {'FAILED' if fails else 'RECEIVED'}
    cost = 1 if fails else 3
    assert [row['delta'] for row in charges] == [{'estimated_tokens': cost}] * 2
    assert all(row['before']['estimated_tokens'] == 0 for row in charges)
    assert all(row['source_units'] == {'character_count': 'PYTHON_LEN_CODEPOINTS',
        'prompt_chars': 7, 'response_chars': 0 if fails else 5, 'includes_system': False} for row in charges)
    assert len({row['budget_ref'] for row in charges}) == 1
    assert charges[0]['budget_epoch'] < charges[1]['budget_epoch']
    physical = events(trace, 'backend_request_context')
    assert len(physical) == 1
    assert physical[0]['data']['physical_request'] is True
    assert physical[0]['data']['request_kind'] == 'GENERATION'
    assert physical[0]['data']['request_boundary'] == 'backend.generate'
    assert physical[0]['data']['provider_budget_ref'] == charges[0]['budget_ref']


def test_provider_charges_received_overflow_but_preflight_denial_has_no_charge(trace):
    adapter = provider(lambda prompt: 'x' * 100, budget=BudgetSnapshot(token_limit=10))
    with pytest.raises(BudgetExceeded):
        adapter.select('p', 'oversized')
    with pytest.raises(BudgetExceeded):
        adapter.select('next', 'oversized')
    charges = events(trace, 'budget_charged', 'PROVIDER')
    assert len(charges) == 1 and charges[0]['data']['delta'] == {'estimated_tokens': 25}
    assert charges[0]['data']['before']['estimated_tokens'] == 0
    assert charges[0]['data']['after']['estimated_tokens'] == adapter._tokens_used == 25
    rejected = events(trace, 'provider_budget_rejected', 'PROVIDER')
    assert [row['data']['budget_phase'] for row in rejected] == ['RECEIVED', 'PRECHECK']
    assert all(row['data']['budget_ref'] == charges[0]['data']['budget_ref'] for row in rejected)
    assert events(trace, 'budget_configured', 'PROVIDER')[0]['data']['limits']['token_limit'] == 10


def test_failed_replay_overflow_is_accounted_without_claiming_a_received_response(trace):
    calls = []

    def fail(prompt):
        calls.append(prompt)
        raise OSError('offline')

    adapter = provider(fail, budget=BudgetSnapshot(token_limit=100))
    with pytest.raises(ProviderUnavailable):
        adapter.select('abcdefgh', 'failed-replay', ordinal=1)
    adapter.budget = BudgetSnapshot(token_limit=1)
    adapter.start_run('failed-replay')
    with pytest.raises(BudgetExceeded):
        adapter.select('abcdefgh', 'failed-replay', ordinal=1)
    assert calls == ['abcdefgh']
    rejected = events(trace, 'provider_budget_rejected', 'PROVIDER')[-1]['data']
    assert rejected['budget_phase'] == 'FAILED_RECEIPT'
    assert rejected['replay'] is True and rejected['exchange_outcome'] == 'FAILED'
    charged = events(trace, 'budget_charged', 'PROVIDER')[-1]['data']
    assert charged['delta'] == {'estimated_tokens': 2}
    assert charged['after']['estimated_tokens'] == adapter._tokens_used == 2
    assert charged['source_units']['response_chars'] == 0


def test_zero_window_cap_and_reconfiguration_preserve_actual_global_counter(trace):
    adapter = provider(budget=BudgetSnapshot(token_limit=1))
    adapter.configure_probe_windows(('0',), 0)
    adapter.enter_probe_window('0')
    assert adapter.select('eightchr', 'unlimited') == '1'
    assert adapter._tokens_used == 2  # V2 zero disables this cap, including the base token cap.
    adapter.configure_probe_windows(('0',), 0)
    adapter.enter_probe_window('0')
    assert adapter.select('newbytes', 'unlimited') == '1'
    charges = [row['data'] for row in events(trace, 'budget_charged', 'PROVIDER')]
    assert [row['after']['estimated_tokens'] for row in charges] == [2, 4]
    assert [row['after']['window_estimated_tokens'] for row in charges] == [2, 2]
    assert charges[0]['budget_ref'] == charges[1]['budget_ref']
    assert charges[0]['budget_epoch'] < charges[1]['budget_epoch']
    reset = events(trace, 'budget_reset', 'PROVIDER')[-1]['data']
    assert reset['scope'] == 'SOURCE_WINDOW'
    assert reset['before']['estimated_tokens'] == reset['after']['estimated_tokens'] == 2
    assert reset['before']['window_estimated_tokens_by_key'] == {'0': 2}
    assert reset['after']['window_estimated_tokens_by_key'] == {'0': 0}


def test_proposal_allowances_remain_independent_of_token_accounting(trace):
    adapter = provider(budget=BudgetSnapshot(tp_calls=1, lexical_calls=1, token_limit=100))
    assert adapter.propose_local('structure', 'proposal-run') == '1'
    assert adapter.propose_lexical('lexical', 'proposal-run') == '1'
    with pytest.raises(BudgetExceeded):
        adapter.propose_local('blocked', 'proposal-run')
    with pytest.raises(BudgetExceeded):
        adapter.propose_lexical('blocked', 'proposal-run')
    charges = [row['data'] for row in events(trace, 'budget_charged', 'PROVIDER')]
    assert [row['delta'] for row in charges] == [
        {'tp_calls': 1}, {'estimated_tokens': 2}, {'lexical_calls': 1}, {'estimated_tokens': 2}]
    assert [row['data']['dimension'] for row in events(trace, 'provider_budget_rejected', 'PROVIDER')] == [
        'tp_calls', 'lexical_calls']
    assert adapter._tp_calls_left == adapter._lexical_calls_left == 0


def test_format_repair_has_two_attempt_charges_at_each_boundary(trace):
    replies = iter(['invalid reply', '1'])
    selector = BoundedExecutor(RealBackendSelector(SimpleNamespace(generate=lambda prompt, **kwargs: next(replies))), ProbeLimits())
    state = FormalizationState('repair', 1, 1, 'text')
    decision = Decision('slot', 'frame', ('c0',))
    schema = DecisionSchema('test', {'c0': Relation('c0', 'meaning', 0, (), 'meaning')})
    prompt = build_selector_prompt(selector, slot_id=decision.slot_id, frame_id=decision.frame_id,
        context_span='text', mentions={}, schema=schema, candidates=decision.candidates)
    with phase('T2_REGIONS'):
        reply = exchange(state, selector, decision, prompt, schema, decision.candidates, 8192)
    assert reply.outcome == 'ONE_SELECTED'
    for level, counter in [('STATE_CALLS', 'llm_calls'), ('EXECUTOR', 'calls'), ('PROVIDER', 'estimated_tokens')]:
        charges = [row['data'] for row in events(trace, 'budget_charged', level)]
        assert len(charges) == 2
        assert [row['selection_attempt'] for row in charges] == [0, 1]
        assert all(row['delta'][counter] > 0 for row in charges)
        assert all(row['pipeline_stage'] == 'T2_REGIONS' for row in charges)
    assert len(events(trace, 'backend_request_context')) == 2
    assert state.budget.llm_calls == selector.calls == 2


def test_state_attempt_can_be_charged_before_executor_gate_without_provider_cost(trace):
    selector = BoundedExecutor(RealBackendSelector(SimpleNamespace(generate=lambda prompt, **kwargs: '1')),
        ProbeLimits(max_prompt_chars=1))
    state = FormalizationState('gate', 1, 1, 'text')
    decision = Decision('slot', 'frame', ('c0',))
    schema = DecisionSchema('test', {'c0': Relation('c0', 'meaning', 0, (), 'meaning')})
    prompt = build_selector_prompt(selector, slot_id=decision.slot_id, frame_id=decision.frame_id,
        context_span='text', mentions={}, schema=schema, candidates=decision.candidates)
    with pytest.raises(BudgetExceeded):
        exchange(state, selector, decision, prompt, schema, decision.candidates, 8192)
    assert state.budget.llm_calls == 1 and selector.calls == 0
    assert len(events(trace, 'budget_charged', 'STATE_CALLS')) == 1
    assert events(trace, 'budget_charged', 'EXECUTOR') == []
    assert events(trace, 'budget_charged', 'PROVIDER') == []
    assert events(trace, 'backend_request_context') == []


def test_observer_snapshot_failure_never_replaces_budget_semantics(trace, monkeypatch):
    class UnprintableError(RuntimeError):
        def __str__(self):
            raise RuntimeError('cannot print')

    def fail(*args, **kwargs):
        raise UnprintableError()

    monkeypatch.setattr(budget_tracing, '_state_snapshot', fail)
    budget = Budget(llm_limit=1)
    budget.spend_llm()
    assert budget.llm_calls == 1 and budget.llm_exhausted
    assert events(trace, 'trace_capture_failed')


def test_logging_does_not_change_canonical_budget_or_provider_accounting(trace):
    results = []
    for logged in (False, True):
        sink = runtime_trace.active_trace() if logged else None
        with runtime_trace.use_trace(sink):
            budget = Budget(probe_scope_limits={'0': 0}, probe_scope_key='0')
            adapter = provider(budget=BudgetSnapshot(token_limit=10))
            for _ in range(2):
                budget.spend_llm()
                assert adapter.select('request', 'same-run', ordinal=1) == '1'
            record = dict(adapter._log.lookup('same-run', 1))
            record.pop('response_time_ms')
            results.append((asdict(budget), budget.llm_exhausted, adapter._tokens_used, record))
    assert results[0] == results[1]
