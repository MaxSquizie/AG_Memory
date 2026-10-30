"""Historical membership, runtime applicability and conditional proof scopes."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass,asdict
from .canonical_ledger import digest
from .composition_dispatcher import canonical

_active=ContextVar('structural_hypothesis',default=None)


def execution_basis(state,cfg):
    from .composition_session import current
    from .structural_probe_inputs import source_signature
    runtime=current(state)
    return canonical({'source_basis':source_signature(state),'context_version':state.context_version,
        'input_scope':runtime.input_signature() if runtime else None,
        'context':{'request':runtime.area_inputs[2] if runtime and runtime.area_inputs else None,
            'constraints':cfg.get('_task_constraints'),'constraints_text':cfg.get('_task_constraints_text'),
            'ownership_feedback':cfg.get('_ownership_feedback'),
            'parent_feedback':runtime.tasks.feedback if runtime else None,
            'memory_context':runtime.context_signature() if runtime else None,
            'morphology_scope':runtime.morphology_scope if runtime else None,
            'domain_feedback':runtime.domain_feedback if runtime else None}})


def origin(state,domain_ref):
    return next((r.get('execution_basis') for r in reversed(state.syntax_trace)
        if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref')==domain_ref),None)


def applicable(state,forest,cfg):
    from .structural_forest import live
    basis=origin(state,forest['membership']['domain_ref'])
    return bool(live(state,forest) and basis and basis==execution_basis(state,cfg)
                and forest['context']==basis['context'] and forest['input_scope']==basis['input_scope'])


@dataclass(frozen=True)
class ConditionalHypothesis:
    forest: dict
    hypothesis_ref: str
    candidate: dict
    basis: dict

    def record(self):return deepcopy(asdict(self))

    def live(self,state):
        from .structural_forest import live
        from .structural_probe_inputs import source_signature
        return (live(state,self.forest) and self.basis==origin(state,self.forest['membership']['domain_ref'])
            and self.basis.get('source_basis')==source_signature(state)
            and self.basis.get('context_version')==state.context_version
            and any(h['hypothesis_ref']==self.hypothesis_ref and h['candidate']==self.candidate
                    for h in self.forest['hypotheses']))

    def wording(self):
        return ('\nInvestigate this interpretation CONDITIONALLY: '+self.candidate['label']+
                '. It is one admissible hypothesis, not a selected fact. All answers here apply only under this hypothesis.')


def active(state):
    value=_active.get()
    if value is None or value[0] is not state:return None
    _,condition,cfg=value
    if not condition.live(state) or condition.basis!=execution_basis(state,cfg):return None
    return condition


def declared(state):
    value=_active.get()
    return value is not None and value[0] is state


@contextmanager
def branch(state,forest,hypothesis,cfg):
    if not applicable(state,forest,cfg):raise ValueError('STRUCTURAL_CONDITION_INAPPLICABLE')
    condition=ConditionalHypothesis(deepcopy(forest),hypothesis['hypothesis_ref'],
        deepcopy(hypothesis['candidate']),deepcopy(origin(state,forest['membership']['domain_ref'])))
    if not condition.live(state):raise ValueError('STRUCTURAL_CONDITION_UNGROUNDED')
    token=_active.set((state,condition,deepcopy(cfg)))
    try:yield condition
    finally:_active.reset(token)


def historical(state,record):
    try:return ConditionalHypothesis(**record).live(state)
    except (TypeError,KeyError):return False
