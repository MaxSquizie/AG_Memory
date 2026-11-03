"""Observation-only identities and receipts for independent budget owners.

The registry belongs to a TSV writer, never to a dataclass, WAL record or
canonical state. Shared Budget objects therefore have one identity, while a
deep copy or a nested executor has its own. Only ``delta`` on ``budget_charged``
is additive; window counters in before/after are views of that same charge.
"""
from functools import wraps
from threading import RLock
import weakref


_writers = {}
_lock = RLock()
TOKEN_ESTIMATE = 'MAX_ONE_FLOOR_PROMPT_RESPONSE_CHARS_DIV_4_V1'


def _runtime():
    from ah.diagnostics import runtime_trace
    return runtime_trace


def _safe(function):
    @wraps(function)
    def observe(*args, **kwargs):
        try:
            runtime = _runtime()
            if not runtime.enabled():
                return None
            return function(*args, **kwargs)
        except Exception as exc:
            try:
                _runtime().emit('trace_capture_failed', status='ERROR',
                    observer=function.__name__, error_type=type(exc).__name__,
                    reason=_runtime().error_text(exc))
            except Exception:
                pass
            return None
    return observe


class _Writer:
    def __init__(self, writer):
        self.writer = weakref.ref(writer)
        self.owners = {}
        self.sequence = 0


class _Owner:
    def __init__(self, owner, reference):
        self.owner = weakref.ref(owner)
        self.reference = reference
        self.epoch = 0
        self.configuration = None
        self.metadata = {}


def _owner(owner, level):
    writer = _runtime().active_trace()
    writer_id = id(writer)
    with _lock:
        registry = _writers.get(writer_id)
        if registry is None or registry.writer() is not writer:
            registry = _Writer(writer)
            _writers[writer_id] = registry

            def retire_writer(reference):
                with _lock:
                    if _writers.get(writer_id) is registry:
                        _writers.pop(writer_id, None)

            registry.writer = weakref.ref(writer, retire_writer)
        key = (id(owner), level)
        entry = registry.owners.get(key)
        if entry is None or entry.owner() is not owner:
            registry.sequence += 1
            entry = _Owner(owner, 'budget:' + level.lower() + ':' + str(registry.sequence))
            registry.owners[key] = entry

            def retire_owner(reference):
                with _lock:
                    if registry.owners.get(key) is entry:
                        registry.owners.pop(key, None)

            entry.owner = weakref.ref(owner, retire_owner)
        return entry


def _identity(owner, level):
    entry = _owner(owner, level)
    return {'budget_level': level, 'budget_ref': entry.reference,
            'budget_epoch': entry.epoch}


@_safe
def identity(owner, level):
    return _identity(owner, level)


def _emit(event, owner, level, **fields):
    _runtime().emit(event, **_identity(owner, level), **fields)


def _configured(owner, level, *, scope, units, limits, counters, reason,
                metadata=None, run_id=None):
    entry = _owner(owner, level)
    if metadata:
        entry.metadata.update(metadata)
    context = _runtime().current_context()
    dimensions = {'run_id': run_id} if run_id is not None else {}
    description = {'scope': scope, 'units': units, 'limits': limits, **entry.metadata}
    signature = _runtime().encode_json({**description,
        'trace_id': context.get('trace_id'), 'run_id': run_id or context.get('run_id')})
    with _lock:
        if entry.configuration == signature:
            return
        entry.configuration = signature
    _emit('budget_configured', owner, level, reason=reason,
          counters=counters, **description, **dimensions)


@_safe
def event(name, owner, level, **fields):
    _emit(name, owner, level, **fields)


def _reset(owner, level, *, before, after, scope, reason, **fields):
    entry = _owner(owner, level)
    with _lock:
        entry.epoch += 1
        entry.configuration = None
    _emit('budget_reset', owner, level, before=before, after=after,
          scope=scope, reason=reason, **fields)


def _state_snapshot(budget):
    key = budget.probe_scope_key
    return {'llm_calls': budget.llm_calls, 'llm_failed': budget.llm_failed,
            'window_calls': budget.probe_scope_calls.get(key, 0)
            if key in budget.probe_scope_limits else None}


def _state_configured(budget, reason, metadata=None):
    _configured(budget, 'STATE_CALLS', reason=reason,
        scope='SOURCE_WINDOW' if budget.probe_scope_limits else 'RUN',
        units={'llm_calls': 'SELECTOR_ATTEMPTS', 'llm_failed': 'FAILED_SELECTOR_ATTEMPTS'},
        limits={'llm_limit': budget.llm_limit,
                'calls_per_window': dict(budget.probe_scope_limits)},
        counters={**_state_snapshot(budget),
                  'window_calls_by_key': dict(budget.probe_scope_calls)},
        metadata={'window_starts': list(budget.probe_window_starts),
                  'window_zero_means_unlimited': True,
                  'run_zero_means_unlimited': False,
                  'accounting_boundary': 'Budget.spend_llm',
                  'physical_requests': False, **(metadata or {})})


@_safe
def state_configured(budget, *, reason='observed'):
    _state_configured(budget, reason)


@_safe
def state_before(budget):
    _state_configured(budget, 'spend_llm')
    return _state_snapshot(budget)


@_safe
def state_charged(budget, before):
    if before is None:
        return
    after = _state_snapshot(budget)
    _emit('budget_charged', budget, 'STATE_CALLS',
        scope='SOURCE_WINDOW' if budget.probe_scope_limits else 'RUN',
        window_key=budget.probe_scope_key if budget.probe_scope_limits else None,
        before=before, after=after,
        delta={name: after[name] - before[name] for name in ('llm_calls', 'llm_failed')},
        accounting_boundary='Budget.spend_llm', physical_requests=False)


@_safe
def state_checked(budget, exhausted):
    _state_configured(budget, 'llm_exhausted')
    key = budget.probe_scope_key
    windowed = bool(budget.probe_scope_limits)
    missing = windowed and key not in budget.probe_scope_limits
    _emit('budget_checked', budget, 'STATE_CALLS',
        status='EXHAUSTED' if exhausted else 'AVAILABLE',
        reason='PROBE_SCOPE_REQUIRED' if missing else
            'LLM_BUDGET_EXHAUSTED' if exhausted else 'WITHIN_LIMIT',
        scope='SOURCE_WINDOW' if windowed else 'RUN',
        window_key=key if windowed else None,
        limit=budget.probe_scope_limits.get(key) if windowed else budget.llm_limit,
        counters=_state_snapshot(budget), exhausted=exhausted, check_only=True)


@_safe
def state_windows_configured(state, policy, release):
    _state_configured(state.budget, 'source_window_policy', metadata={
        'source_policy': dict(policy), 'resource_snapshot': getattr(release, 'sha256', None),
        'source_window_unit': 'TOKEN_EVIDENCE_ITEMS', 'source_tokens': len(state.evidence),
        'source_chars': len(state.text)})


@_safe
def state_window_entered(state, previous, source_range):
    budget = state.budget
    _state_configured(budget, 'window_enter')
    key = budget.probe_scope_key
    _emit('budget_window_entered', budget, 'STATE_CALLS', scope='SOURCE_WINDOW',
        previous_window_key=previous, window_key=key,
        window_limit=budget.probe_scope_limits.get(key),
        window_used=budget.probe_scope_calls.get(key, 0),
        counters=_state_snapshot(budget), source_range=source_range,
        reentered=previous == key)


def _provider_snapshot(provider, *, all_windows=False):
    window = provider._window_tokens
    key = window.key if window is not None else None
    result = {'estimated_tokens': provider._tokens_used,
              'tp_calls': provider.budget.tp_calls - provider._tp_calls_left,
              'lexical_calls': provider.budget.lexical_calls - provider._lexical_calls_left,
              'window_estimated_tokens': window.used.get(key)
              if window is not None else None}
    if all_windows:
        result['window_estimated_tokens_by_key'] = dict(window.used) if window is not None else {}
    return result


def _provider_configured(provider, reason, *, run_id=None, metadata=None):
    window = provider._window_tokens
    _configured(provider, 'PROVIDER', reason=reason, run_id=run_id,
        scope='SOURCE_WINDOW' if window is not None else 'RUN',
        units={'estimated_tokens': 'ESTIMATED_TEXT_TOKENS',
               'tp_calls': 'STRUCTURAL_PROPOSAL_ATTEMPTS', 'lexical_calls': 'LEXICAL_PROPOSAL_ATTEMPTS'},
        limits={name: getattr(provider.budget, name) for name in
                ('tp_calls', 'lexical_calls', 'max_nodes', 'max_edges', 'max_depth', 'token_limit')} |
               {'tokens_per_window': dict(window.limits) if window is not None else {}},
        counters=_provider_snapshot(provider, all_windows=True),
        metadata={'provider': provider.name, 'model_key': provider.model_key,
                  'accounting_model': TOKEN_ESTIMATE, 'zero_token_limit_means_unlimited': True,
                  'token_cap_scope': 'SOURCE_WINDOW_ONLY' if window is not None else 'RUN',
                  'proposal_call_scope': 'RUN', 'actual_model_usage': False,
                  **(metadata or {})})


@_safe
def provider_configured(provider, *, reason='observed', run_id=None):
    _provider_configured(provider, reason, run_id=run_id)


@_safe
def provider_before(provider, *, all_windows=False):
    return _provider_snapshot(provider, all_windows=all_windows)


@_safe
def provider_reset(provider, before, *, scope, reason, run_id=None, requested_window_limit=None):
    dimensions = {'run_id': run_id} if run_id is not None else {}
    _reset(provider, 'PROVIDER', before=before,
        after=_provider_snapshot(provider, all_windows=True), scope=scope, reason=reason, **dimensions)
    metadata = {'requested_tokens_per_window': requested_window_limit} if scope == 'SOURCE_WINDOW' else None
    _provider_configured(provider, reason, run_id=run_id, metadata=metadata)


@_safe
def provider_tokens_charged(provider, before, cost, *, prompt_chars, response_chars,
                            replay, exchange_outcome):
    window = provider._window_tokens
    _emit('budget_charged', provider, 'PROVIDER',
        scope='SOURCE_WINDOW' if window is not None else 'RUN',
        window_key=window.key if window is not None else None,
        before=before, delta={'estimated_tokens': cost}, after=_provider_snapshot(provider),
        accounting_model=TOKEN_ESTIMATE,
        source_units={'character_count': 'PYTHON_LEN_CODEPOINTS', 'prompt_chars': prompt_chars,
                      'response_chars': response_chars, 'includes_system': False},
        replay=replay, exchange_outcome=exchange_outcome, actual_model_usage=False)


@_safe
def provider_proposal_charged(provider, counter):
    after = _provider_snapshot(provider)
    before = dict(after)
    before[counter] -= 1
    _emit('budget_charged', provider, 'PROVIDER', scope='RUN', window_key=None,
        before=before, delta={counter: 1}, after=after,
        accounting_boundary='PROPOSAL_ALLOWANCE', physical_requests=False)


@_safe
def executor_configured(executor, *, reason='observed'):
    _configured(executor, 'EXECUTOR', reason=reason, scope='EXECUTOR_LIFETIME',
        units={'calls': 'ADMITTED_EXECUTOR_CALLS', 'input_chars': 'INPUT_CHARACTERS',
               'elapsed_seconds': 'WALL_CLOCK_SECONDS'},
        limits={name: getattr(executor.limits, name) for name in
                ('max_calls', 'max_prompt_chars', 'max_input_chars', 'max_elapsed_seconds')},
        counters={'calls': executor.calls, 'input_chars': executor.input_chars},
        metadata={'executor_type': type(executor.executor).__name__,
                  'input_size_contract': 'executor.prompt_size(prompt) if available else len(prompt)',
                  'elapsed_start': 'EXECUTOR_CREATION', 'elapsed_additive': False,
                  'physical_requests': False})


@_safe
def executor_charged(executor, size, elapsed, size_source):
    _emit('budget_charged', executor, 'EXECUTOR', scope='EXECUTOR_LIFETIME', window_key=None,
        before={'calls': executor.calls - 1, 'input_chars': executor.input_chars - size},
        delta={'calls': 1, 'input_chars': size},
        after={'calls': executor.calls, 'input_chars': executor.input_chars},
        elapsed_seconds=elapsed, input_size_source=size_source,
        physical_requests=False)
