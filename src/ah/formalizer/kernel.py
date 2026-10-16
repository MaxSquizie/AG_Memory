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

from .provider_adapter import BudgetExceeded


class ProbeExecutor(Protocol):
    selection_reply_format: str
    def select(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class ProbeLimits:
    max_calls: int = 128
    max_prompt_chars: int = 8192
    max_input_chars: int = 131072
    max_elapsed_seconds: float = 60.0

    def __post_init__(self):
        if any(type(n) is not int or n<1 for n in (self.max_calls,self.max_prompt_chars,self.max_input_chars)):
            raise ValueError('PROBE_LIMIT_INVALID')
        if not isinstance(self.max_elapsed_seconds,(int,float)) or not isfinite(self.max_elapsed_seconds) or self.max_elapsed_seconds<=0:raise ValueError('PROBE_LIMIT_INVALID')


class BoundedExecutor:
    def __init__(self,executor,limits):
        self.executor,self.limits=executor,limits
        self.calls=0;self.input_chars=0;self.started=monotonic()

    def __getattr__(self,key):return getattr(self.executor,key)

    def _charge(self,prompt):
        size=self.executor.prompt_size(prompt) if hasattr(self.executor,'prompt_size') else len(prompt)
        if (self.calls>=self.limits.max_calls or size>self.limits.max_prompt_chars or
            self.input_chars+size>self.limits.max_input_chars or
            monotonic()-self.started>self.limits.max_elapsed_seconds):
            raise BudgetExceeded('COMPUTATION_LIMIT')
        self.calls+=1;self.input_chars+=size

    def select(self,prompt):
        self._charge(prompt)
        return self.executor.select(prompt)

    def propose_local(self,prompt):
        self._charge(prompt)
        return self.executor.propose_local(prompt)


@dataclass
class KernelResult:
    state: object
    metrics: dict = field(default_factory=dict)


def interpret(text,*,executor: ProbeExecutor,release,observation,morph=None,context_reader=None,limits=None):
    """Interpret one source with caller-owned IDs and an immutable context copy.

    source/version/resource validation remains the ordinary V7 validation.
    Elapsed budget is checked between probes; host transport owns call timeouts.
    """
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
