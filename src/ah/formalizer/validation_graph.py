"""Run-local, read-only evaluation of proof obligations without Python recursion.

Only private validation views are interned. Their equivalence includes every
field read by validators: unchanged base state, all decisions/probe records,
latest task/domain records and the union of retirement events. Trace history
is never rewritten in the executing formalizer.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import copy
from hashlib import sha256
from pickle import dumps

_current=ContextVar('validation_graph',default=None)


def request(kind,state,payload,**options):return kind,state,payload,options


def expand(item):
    kind,state,payload,options=item
    if kind=='CONDITION':
        from .structural_conditions import _historical
        return _historical(state,payload)
    if kind=='FOREST':
        from .structural_forest import _live
        return _live(state,payload)
    if kind=='DOMAIN':
        from .partial_readings import _valid_domain
        return _valid_domain(state,payload)
    if kind=='SHELL':
        from .structural_shells import _live
        return _live(state,payload)
    if kind=='PROOF':
        from .structural_tasks import _licensed_impl
        return _licensed_impl(state,payload,**options)
    if kind=='EXCLUSION':
        from .partition_exclusions import _live
        return _live(state,payload)
    raise ValueError('VALIDATION_OBLIGATION_UNKNOWN')


class ValidationGraph:
    def __init__(self):
        self.results={};self.owners={};self.views={};self.view_keys={}
        self.hashes={};self.sources={};self.running=False
        self.stats={'obligations':0,'cache_hits':0,'views':0,'view_hits':0,'maximum_pending':0}

    def hashed(self,value):
        entry=self.hashes.get(id(value))
        if entry is None:
            # This is only a transient identity, never a persisted proof hash.
            # Preserve Python container/class distinctions used by validators' ==.
            # Serialization is write-only; no unpickling or external cache exists.
            entry=(value,sha256(dumps(value,protocol=5)).hexdigest())
            self.hashes[id(value)]=entry
        return entry[1]

    def key(self,item):
        kind,state,payload,options=item
        self.owners[id(state)]=state
        return kind,id(state),self.hashed(payload),self.hashed(options)

    def source(self,state):
        base=self.view_keys.get(id(state),(id(state),))[0]
        if base not in self.sources:
            from .structural_probe_inputs import source_signature
            self.sources[base]=source_signature(state)
        return self.sources[base]

    def overlay(self,state,evidence):
        from .state import Decision,Ground
        from .partial_readings import retired_refs
        # Preserve current authority: packet data only fills absent decisions.
        local=copy(state);local.decisions=dict(state.decisions)
        local.component_probe_records=dict(state.component_probe_records)
        for key,raw in evidence['decisions'].items():
            if key not in local.decisions:
                local.decisions[key]=Decision(**{**raw,'grounds':[Ground(**g) for g in raw['grounds']]})
        for key,record in evidence['probes'].items():local.component_probe_records.setdefault(key,record)
        local.syntax_trace=list(evidence['trace'])+state.syntax_trace
        domains={};tasks={};latest_tasks={}
        for row in local.syntax_trace:
            if row.get('kind')=='TASK_DOMAIN':domains[row.get('task_ref')]=row
            elif row.get('kind')=='STRUCTURAL_TASK':
                tasks[(row.get('decision_ref'),row.get('selected'))]=row
                latest_tasks[row.get('decision_ref')]=row
        base=self.view_keys.get(id(state),(id(state),))[0]
        signature=(base,
            tuple(sorted((k,self.hashed(v)) for k,v in local.decisions.items())),
            tuple(sorted((k,self.hashed(v)) for k,v in local.component_probe_records.items())),
            frozenset((k,self.hashed(v)) for k,v in domains.items()),
            frozenset((k,self.hashed(v)) for k,v in tasks.items()),
            frozenset((k,self.hashed(v)) for k,v in latest_tasks.items()),
            frozenset(retired_refs(local.syntax_trace)))
        existing=self.views.get(signature)
        if existing is not None:
            self.stats['view_hits']+=1;return existing
        self.views[signature]=local;self.view_keys[id(local)]=signature
        self.owners[id(state)]=state;self.owners[id(local)]=local
        self.stats['views']+=1
        return local

    def run(self,item):
        if self.running:raise RuntimeError('RECURSIVE_VALIDATION_ENTRY')
        self.running=True;stack=[];grey=set()
        def push(task):
            key=self.key(task);grey.add(key)
            stack.append([key,expand(task),None]);self.stats['obligations']+=1
            self.stats['maximum_pending']=max(self.stats['maximum_pending'],len(stack))
        try:
            root=self.key(item)
            if root in self.results:return self.results[root]
            push(item)
            while stack:
                key,generator,value=stack[-1]
                try:child=generator.send(value)
                except (StopIteration,KeyError,TypeError,ValueError) as done:
                    # Invalid persisted evidence fails closed; control errors such
                    # as recursive entry are not swallowed.
                    result=bool(done.value) if isinstance(done,StopIteration) else False;self.results[key]=result;grey.remove(key);stack.pop()
                    if stack:stack[-1][2]=result
                    continue
                child_key=self.key(child)
                if child_key in grey:
                    stack[-1][2]=False
                elif child_key in self.results:
                    self.stats['cache_hits']+=1;stack[-1][2]=self.results[child_key]
                else:push(child)
            return self.results[root]
        finally:
            for _,generator,_ in stack:generator.close()
            self.running=False


@contextmanager
def scope():
    current=_current.get();token=None
    if current is None:current=ValidationGraph();token=_current.set(current)
    try:yield current
    finally:
        if token is not None:_current.reset(token)


def validate(kind,state,payload,**options):
    with scope() as graph:return graph.run(request(kind,state,payload,**options))


def overlay(state,evidence):
    graph=_current.get()
    if graph is None:raise RuntimeError('VALIDATION_VIEW_OUTSIDE_SCOPE')
    return graph.overlay(state,evidence)


def source(state):
    graph=_current.get()
    if graph is None:
        from .structural_probe_inputs import source_signature
        return source_signature(state)
    return graph.source(state)
