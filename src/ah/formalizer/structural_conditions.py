"""Historical membership, runtime applicability and conditional proof scopes."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass,asdict
from .canonical_ledger import digest
from .composition_dispatcher import canonical

_active=ContextVar('structural_hypothesis',default=None)
_verified=ContextVar('structural_conditions_verified',default=None)


def registry(state):
    return state.observation.setdefault('structural_condition_registry',{})


def resolve(state,record):
    node=registry(state).get(record.get('condition_ref'))
    if node is None or 'condition:'+digest(node)!=record.get('condition_ref'):
        raise ValueError('STRUCTURAL_CONDITION_REFERENCE_INVALID')
    return ConditionalHypothesis(**deepcopy(node))


def register(state,condition):
    node=asdict(condition);ref=condition.record()['condition_ref']
    existing=registry(state).setdefault(ref,deepcopy(node))
    if existing!=node:raise ValueError('STRUCTURAL_CONDITION_ADDRESS_COLLISION')
    domain_ref=condition.forest['membership']['domain_ref']
    domain=next(r for r in reversed(state.syntax_trace) if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref')==domain_ref)
    refs={domain_ref,*domain['page_refs']}
    evidence={'trace':[deepcopy(r) for r in state.syntax_trace
        if r.get('task_ref')==domain_ref or r.get('decision_ref') in refs],
        'decisions':{k:asdict(v) for k,v in state.decisions.items() if k in refs},
        'probes':{k:deepcopy(v) for k,v in state.component_probe_records.items() if k in refs}}
    state.observation.setdefault('structural_condition_evidence',{}).setdefault(ref,evidence)
    return condition



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
    parent_condition_ref: str | None = None
    parent_shell_ref: str | None = None
    child_ref: str | None = None

    def record(self):return {'condition_ref':'condition:'+digest(asdict(self))}

    def live(self,state):
        return historical(state,self.record())

    def local_live(self,state):
        if bool(self.parent_condition_ref)!=bool(self.parent_shell_ref and self.child_ref):return False
        from .structural_shells import evidence_state
        packet=state.observation.get('structural_condition_evidence',{}).get(self.record()['condition_ref'])
        if packet is None:return False
        state=evidence_state(state,{'evidence':packet},read_only=True)
        from .structural_forest import live
        from .structural_probe_inputs import source_signature
        domain=next((r for r in reversed(state.syntax_trace) if r.get('kind')=='TASK_DOMAIN'
            and r.get('task_ref')==self.forest['membership']['domain_ref']),{})
        expected={'condition_ref':self.parent_condition_ref} if self.parent_condition_ref else None
        return (domain.get('branch_condition')==expected and live(state,self.forest) and self.basis==origin(state,self.forest['membership']['domain_ref'])
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
    _,condition,cfg,execution=value
    if not condition.live(state) or execution!=execution_basis(state,cfg):return None
    return condition


def declared(state):
    value=_active.get()
    return value is not None and value[0] is state


@contextmanager
def branch(state,forest,hypothesis,cfg):
    if not applicable(state,forest,cfg):raise ValueError('STRUCTURAL_CONDITION_INAPPLICABLE')
    inherited=active(state)
    parent_ref=inherited.record()['condition_ref'] if inherited else None
    edge=getattr(current_runtime(state),'structural_child_edge',None)
    condition=register(state,ConditionalHypothesis(deepcopy(forest),hypothesis['hypothesis_ref'],
        deepcopy(hypothesis['candidate']),deepcopy(origin(state,forest['membership']['domain_ref'])),
        parent_ref,edge[0] if edge else None,edge[1] if edge else None))
    if not condition.live(state):raise ValueError('STRUCTURAL_CONDITION_UNGROUNDED')
    token=_active.set((state,condition,deepcopy(cfg),execution_basis(state,cfg)))
    try:yield condition
    finally:_active.reset(token)



def current_runtime(state):
    from .composition_session import current
    return current(state)


def historical(state,record):
    verified=_verified.get();outer=verified is None
    token=_verified.set({}) if outer else None
    views=_verified.get()
    # Keep the view alive: Python may otherwise reuse its id during this check.
    owner,verified=views.setdefault(id(state),(state,set()))
    chain=[];seen=set()
    try:
        ref=record.get('condition_ref')
        while ref:
            if ref in seen:return False
            if ref in verified:break
            seen.add(ref);node=resolve(state,{'condition_ref':ref})
            chain.append((ref,node));ref=node.parent_condition_ref
        for ref,node in reversed(chain):
            if not node.local_live(state):return False
            if node.parent_condition_ref:
                shell=state.observation.get('structural_shell_registry',{}).get(node.parent_shell_ref)
                if shell is None or shell['condition']!={'condition_ref':node.parent_condition_ref}:return False
                from .structural_shells import live
                if not live(state,shell):return False
                child=next((c for c in shell['children'] if c['child_ref']==node.child_ref),None)
                if child is None or child['token_refs']!=node.forest['token_refs']:return False
                if child['input_slot']!=node.basis['context']['request']:return False
            verified.add(ref)
        return bool(record.get('condition_ref'))
    except (TypeError,KeyError,ValueError):return False
    finally:
        if outer:_verified.reset(token)


def allows(state,required,current):
    if not historical(state,current):return False
    ref=current['condition_ref'];seen=set()
    while ref and ref not in seen:
        if required=={'condition_ref':ref}:return historical(state,required)
        seen.add(ref);ref=resolve(state,{'condition_ref':ref}).parent_condition_ref
    return False


@contextmanager
def child_scope(state,shell,child,cfg):
    """A validated parent slot licenses a new input, not equality with its parent."""
    from .structural_shells import live
    if not live(state,shell) or child not in shell['children']:
        raise ValueError('STRUCTURAL_CHILD_UNGROUNDED')
    basis=execution_basis(state,cfg)
    runtime=current_runtime(state)
    if (runtime is None or runtime.area_inputs is None
            or [t.token_id for t in runtime.area_inputs[1]]!=child['token_refs']
            or canonical(runtime.area_inputs[2])!=child['input_slot']):
        raise ValueError('STRUCTURAL_CHILD_INPUT_CHANGED')
    condition=resolve(state,shell['condition'])
    previous=getattr(runtime,'structural_child_edge',None)
    runtime.structural_child_edge=(shell['shell_ref'],child['child_ref'])
    token=_active.set((state,condition,deepcopy(cfg),basis))
    try:yield condition
    finally:
        _active.reset(token);runtime.structural_child_edge=previous


@contextmanager
def inherit_scope(source,target,cfg,condition=None):
    condition=condition or active(source)
    if condition is None:
        yield
        return
    token=_active.set((target,condition,deepcopy(cfg),execution_basis(target,cfg)))
    try:yield
    finally:_active.reset(token)


@contextmanager
def validation_scope():
    """Share verified ancestors only during one synchronous read-only check."""
    token=_verified.set({}) if _verified.get() is None else None
    try:yield
    finally:
        if token is not None:_verified.reset(token)
