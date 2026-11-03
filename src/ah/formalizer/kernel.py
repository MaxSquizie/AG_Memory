"""Store-independent formalizer component and bounded provider interface.

The host owns resources, context access, replay and persistence. This component
returns an interpretation; it never commits facts. Executors, including future
non-LLM probe engines, implement the same closed-selection wire contract.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic
from typing import Protocol
from math import isfinite
from ah.diagnostics import runtime_trace

from .provider_adapter import BudgetExceeded, capture_provider_payload
from .runtime_tracing import traced
from . import budget_tracing


class ProbeExecutor(Protocol):
    selection_reply_format: str
    def select(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class ProbeLimits:
    max_calls: int = 1024
    max_prompt_chars: int = 8192
    max_input_chars: int = 4194304
    max_elapsed_seconds: float = 3600.0

    def __post_init__(self):
        if any(type(n) is not int or n<1 for n in (self.max_calls,self.max_prompt_chars,self.max_input_chars)):
            raise ValueError('PROBE_LIMIT_INVALID')
        if not isinstance(self.max_elapsed_seconds,(int,float)) or not isfinite(self.max_elapsed_seconds) or self.max_elapsed_seconds<=0:raise ValueError('PROBE_LIMIT_INVALID')


class BoundedExecutor:
    def __init__(self,executor,limits):
        self.executor,self.limits=executor,limits
        self.calls=0;self.input_chars=0;self.started=monotonic()
        budget_tracing.executor_configured(self, reason='created')

    def __getattr__(self,key):return getattr(self.executor,key)

    def _charge(self,prompt):
        budget_tracing.executor_configured(self, reason='precheck')
        custom_size=hasattr(self.executor,'prompt_size')
        size=self.executor.prompt_size(prompt) if custom_size else len(prompt)
        checks=(('calls',self.calls+1,self.limits.max_calls),
                ('prompt_chars',size,self.limits.max_prompt_chars),
                ('input_chars',self.input_chars+size,self.limits.max_input_chars),
                ('elapsed_seconds',monotonic()-self.started,self.limits.max_elapsed_seconds))
        for dimension,used,maximum in checks:
            if used>maximum:
                budget_tracing.event('executor_budget_rejected', self, 'EXECUTOR', status='BLOCKED',
                    reason='COMPUTATION_LIMIT', dimension=dimension,
                    used=used, maximum=maximum, calls=self.calls,
                    input_chars=self.input_chars, scope='EXECUTOR_LIFETIME',
                    elapsed_seconds=checks[-1][1])
                raise BudgetExceeded('COMPUTATION_LIMIT',f'{dimension}: {used} > {maximum}')
        self.calls+=1;self.input_chars+=size
        budget_tracing.executor_charged(self, size, checks[-1][1],
            'PROMPT_SIZE_HOOK' if custom_size else 'LEN_PROMPT')

    def _execute(self, operation, prompt):
        if not runtime_trace.enabled():
            self._charge(prompt)
            return getattr(self.executor, operation)(prompt)
        identity = budget_tracing.identity(self, 'EXECUTOR') or {}
        with (runtime_trace.bind(executor_budget_ref=identity.get('budget_ref')),
              runtime_trace.span('EXECUTOR', operation=operation,
                executor_type=type(self.executor).__name__) as outcome):
            budget_tracing.executor_configured(self, reason='request')
            with capture_provider_payload() as captured:
                if not captured['request'] or captured.get('request_value') is not prompt:
                    runtime_trace.emit('executor_request', operation=operation,
                        prompt=prompt, selection_audit=getattr(prompt, 'selection_audit', None),
                        payload_source='EXECUTOR')
                    captured.update(request=True, request_value=prompt)
                returned = False
                raw = None
                try:
                    self._charge(prompt)
                    raw = getattr(self.executor, operation)(prompt)
                    returned = True
                    outcome['status'] = 'RETURNED'
                    return raw
                except BudgetExceeded as exc:
                    outcome.update(status='BLOCKED', reason=exc.code)
                    raise
                finally:
                    # Live calls already recorded their receipt. A standalone
                    # executor or a wrapper that changes the response has its
                    # own observable result.
                    if returned and (not captured['response']
                            or captured.get('response_value') is not raw):
                        runtime_trace.emit('executor_response', operation=operation,
                            status='RETURNED', raw_response=raw,
                            payload_source='EXECUTOR')
                        captured.update(response=True, response_value=raw)
                    outcome.update(calls=self.calls, input_chars=self.input_chars,
                        provider_payload_observed=captured['provider'])

    def select(self,prompt):
        return self._execute('select', prompt)

    def propose_local(self,prompt):
        return self._execute('propose_local', prompt)


@dataclass
class KernelResult:
    state: object
    metrics: dict = field(default_factory=dict)


@traced('KERNEL_INTERPRET', mode='component')
def interpret(text,*,executor: ProbeExecutor,release,observation,morph=None,context_reader=None,limits=None):
    """Interpret one source with caller-owned IDs and an immutable context copy.

    source/version/resource validation remains the ordinary V7 validation.
    Elapsed budget is checked between probes; host transport owns call timeouts.
    """
    metadata = observation if isinstance(observation, dict) else {}
    with runtime_trace.bind(observation_id=metadata.get('observation_id'),
            interpretation_version=metadata.get('interpretation_version')):
        with runtime_trace.span('KERNEL', entry_point='kernel.interpret',
                commits_memory=False) as outcome:
            result = _interpret(text, executor=executor, release=release,
                observation=observation, morph=morph,
                context_reader=context_reader, limits=limits)
            outcome.update(status='RETURNED', machine_state=result.state.machine_state,
                metrics=result.metrics)
            return result


def _interpret(text,*,executor,release,observation,morph=None,context_reader=None,limits=None):
    from .native_frontend import run_native
    if not isinstance(text,str) or not observation.get('observation_id'):
        raise ValueError('INPUT_REJECTED')
    if type(observation.get('interpretation_version')) is not int or observation['interpretation_version']<1:
        raise ValueError('INVALID_INTERPRETATION_VERSION')
    bounded=BoundedExecutor(executor,limits or ProbeLimits())
    raw=deepcopy(observation)
    if raw.get('text',text)!=text:raise ValueError('INPUT_TEXT_MISMATCH')
    raw['text']=text;raw.setdefault('structural_contract','region_probes')
    state=run_native(text,bounded,release,raw,morph=morph,context_reader=context_reader)
    return KernelResult(state,{'probe_calls':bounded.calls,'input_chars':bounded.input_chars,
                              'elapsed_seconds':monotonic()-bounded.started})
