"""Dependency-driven, run-local tasks shared by all composition producers.

A changed input invalidates consumers transitively. Unchanged tasks, including
pending ones, are reused; invalidation is not permission to guess or retry a
provider failure. Only requested branches are recomputed.
"""
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from .canonical_ledger import digest


def canonical(value):
    if is_dataclass(value):return canonical(asdict(value))
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [canonical(v) for v in value]
    if isinstance(value,(set,frozenset)):return sorted(canonical(v) for v in value)
    return value


class DispatchBlocked(ValueError):
    pass


class Dispatcher:
    def __init__(self,state,limit=20000):
        self.state=state;self.limit=limit;self.spent=0
        self.nodes={};self.consumers={};self.stack=[]

    def trace(self,kind,key,**fields):
        self.state.syntax_trace.append({'kind':kind,'task_ref':key,
            'task_kind':self.nodes[key]['kind'],**self.nodes[key].get('area',{}),**fields})

    def invalidate(self,key,reason):
        queue=[key];seen=set()
        while queue:
            ref=queue.pop()
            if ref in seen:continue
            seen.add(ref)
            node=self.nodes.get(ref)
            if node is not None:
                node['dirty']=True
                self.trace('DISPATCH_INVALIDATED',ref,reason=reason,changed_task_ref=key)
            queue.extend(self.consumers.get(ref,()))

    def valid(self,key,revision=None,seen=None):
        node=self.nodes.get(key)
        if not node or node['dirty'] or 'result' not in node:return False
        if revision is not None and node['revision']!=revision:return False
        seen=set() if seen is None else seen
        if key in seen:return False
        return all(self.valid(ref,version,seen|{key}) for ref,version in node['reads'].items())

    def replace_read(self,key):
        """A consumer explicitly replaced its tentative child in place."""
        if self.stack:
            self.stack[-1][1][key]=self.nodes[key]['revision']

    def discard_attempt(self):
        """The composer has rejected the entire tentative result.

        Its next revision must subscribe only to dependencies it actually uses.
        The audit history remains; this is not a provider retry instruction.
        """
        if self.stack:
            key,reads=self.stack[-1]
            reads.clear()
            self.trace('DISPATCH_RECHECK',key,reason='REJECTED_COMPOSITION_DISCARDED')

    def run(self,key,inputs,compute,*,kind,source_range=None,token_refs=(),contract=None):
        if any(ref==key for ref,_ in self.stack):
            self.state.diag('COMPOSITION_CYCLE',key)
            raise DispatchBlocked('COMPOSITION_CYCLE')
        signature=digest(canonical(inputs));node=self.nodes.get(key)
        if node is None:
            node={'kind':kind,'signature':signature,'revision':0,'reads':{},'dirty':True}
            from .task_contracts import CONTRACTS,ProducerContract
            node['contract']=asdict(contract or CONTRACTS.get(kind,ProducerContract(kind,'CALLER_DECLARED','CALLER_INPUT','CALLER_RESULT','caller-defined domain','explicit completion')))
            self.nodes[key]=node
        elif node['signature']!=signature:
            self.invalidate(key,'INPUT_CHANGED');node['signature']=signature
        if source_range is not None:node['area']={'source_range':list(source_range),'token_refs':list(token_refs)}
        if self.valid(key):
            self.trace('DISPATCH_REUSED',key,revision=node['revision'])
        else:
            attempts=set()
            while True:
                self.spent+=1
                if self.spent>self.limit:
                    self.state.diag('COMPOSITION_DISPATCH_INCOMPLETE',key)
                    raise DispatchBlocked('COMPOSITION_DISPATCH_INCOMPLETE')
                retired={id(d) for d in node.get('diagnostics',())}
                self.state.diagnostics[:]=[d for d in self.state.diagnostics if id(d) not in retired]
                before=len(self.state.diagnostics)
                reads={};self.stack.append((key,reads))
                try:result=compute()
                finally:self.stack.pop()
                # A dependency changed after it was consumed during this task.
                # Do not publish a mixture of revisions.
                if any(not self.valid(ref,version) for ref,version in reads.items()):
                    attempted=digest([node['signature'],[(ref,self.nodes[ref]['signature']) for ref in sorted(reads)]])
                    if attempted in attempts:
                        self.state.diag('COMPOSITION_DEPENDENCY_NO_PROGRESS',key)
                        raise DispatchBlocked('COMPOSITION_DEPENDENCY_NO_PROGRESS')
                    attempts.add(attempted)
                    self.trace('DISPATCH_RECHECK',key,reason='DEPENDENCY_CHANGED_DURING_TASK')
                    continue
                for ref in node['reads']:self.consumers.get(ref,set()).discard(key)
                for ref in reads:self.consumers.setdefault(ref,set()).add(key)
                nested={id(d) for ref,n in self.nodes.items() if ref!=key for d in n.get('diagnostics',())}
                node['diagnostics']=[d for d in self.state.diagnostics[before:] if id(d) not in nested]
                from .task_contracts import produced
                receipt=produced(kind,result,node['diagnostics']);result=receipt.value
                node['receipt']={'task_outcome':receipt.outcome.value,'search_complete':receipt.search_complete,
                                 'source_complete':receipt.source_complete,'alternatives':list(receipt.alternatives),
                                 'structure_complete':receipt.structure_complete,'write_eligible':receipt.write_eligible}
                node.update(result=deepcopy(result),reads=reads,dirty=False,revision=node['revision']+1)
                self.trace('DISPATCH_COMPLETED',key,revision=node['revision'],
                    contract=node['contract'],**node['receipt'],
                    dependencies=[{'task_ref':ref,'revision':v} for ref,v in reads.items()])
                break
        if self.stack:self.stack[-1][1].setdefault(key,node['revision'])
        return deepcopy(node['result'])
