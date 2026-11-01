"""Source-local read capture, including dispatcher cache hits.

This is observation, not task completion. Conflicting or retired dependencies
keep a produced candidate pending; they never prove that reading impossible.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from hashlib import sha256
from pickle import dumps

_active=ContextVar('producer_reads',default=None)


class Reads:
    def __init__(self,dispatcher):
        self.dispatcher=dispatcher;self.external={};self.roots={}

    def observe(self,kind,value,expected=True,record=None):
        from .dispatch_evidence import observation_address
        address=observation_address(kind,value,expected)
        key=sha256(dumps([kind,address],protocol=5)).hexdigest()
        from .dispatch_evidence import read_record,retain_read
        record=deepcopy(record) if record is not None else read_record(self.dispatcher.state,kind,value,expected)
        self.external[key]=retain_read(self.external.get(key),record)

    def task(self,key):
        # Nested and abandoned attempts are represented only by the final
        # successful outer task's dependency closure.
        if self.dispatcher.stack:return
        pending=[key];nodes={}
        while pending:
            ref=pending.pop()
            if ref in nodes:continue
            node=self.dispatcher.nodes.get(ref)
            if node is None:continue
            nodes[ref]=deepcopy({k:node.get(k) for k in ('kind','revision','reads','evidence_reads','probe_stamp')})
            pending.extend(node.get('reads',{}))
        revision=self.dispatcher.nodes[key]['revision']
        self.roots.setdefault(key,{})[revision]=nodes

    def discard(self,refs):
        from .dispatch_evidence import read_probe_refs
        refs=set(refs)
        for ref in refs:self.roots.pop(ref,None)
        def depends(row):
            return {'probe:'+ref for ref in read_probe_refs(self.dispatcher.state,row)} & refs
        for root,versions in self.roots.items():
            for nodes in versions.values():
                for ref in refs:nodes.pop(ref,None)
                for node in nodes.values():
                    node['reads']={ref:v for ref,v in (node.get('reads') or {}).items() if ref not in refs}
                    node['evidence_reads']={k:r for k,r in (node.get('evidence_reads') or {}).items() if not depends(r)}
                reachable=set();pending=[root]
                while pending:
                    ref=pending.pop()
                    if ref in reachable or ref not in nodes:continue
                    reachable.add(ref);pending.extend(nodes[ref].get('reads') or {})
                for ref in list(nodes):
                    if ref not in reachable:nodes.pop(ref)
        for key,row in list(self.external.items()):
            used={'probe:'+ref for ref in read_probe_refs(self.dispatcher.state,row)}
            if used & refs:self.external.pop(key)

    def snapshot(self):
        # Do not replay cached reads into the chronological direct-read map:
        # both sets are obligations, not assignments that can overwrite one
        # another based on traversal order.
        external=dict(self.external);probes={};consistent=True;contexts=set()
        for versions in self.roots.values():
            for nodes in versions.values():
                for ref,node in nodes.items():
                    if node['kind']=='GOAL_CONTEXT':contexts.add(ref)
                    if node['kind']=='PROBE':
                        probe=ref.removeprefix('probe:');stamp=node.get('probe_stamp')
                        if probe in probes and probes[probe]!=stamp:consistent=False
                        probes[probe]=stamp
                    for read in (node.get('evidence_reads') or {}).values():
                        key=sha256(dumps(read,protocol=5)).hexdigest()
                        external[key]=deepcopy(read)
        return {'probes':probes,'external':deepcopy(list(external.values())),
                'consistent':consistent,'contexts':sorted(contexts)}


@contextmanager
def capture(dispatcher):
    reads=Reads(dispatcher);token=_active.set(reads)
    try:yield reads
    finally:_active.reset(token)


def capturing(dispatcher):
    reads=_active.get()
    return reads is not None and reads.dispatcher is dispatcher


def observe(dispatcher,kind,value,expected,record=None):
    reads=_active.get()
    if reads is not None and reads.dispatcher is dispatcher and not dispatcher.checking_evidence and not dispatcher.stack:
        reads.observe(kind,value,expected,record)


def task(dispatcher,key):
    reads=_active.get()
    if reads is not None and reads.dispatcher is dispatcher:reads.task(key)


def discard(dispatcher,refs):
    reads=_active.get()
    if reads is not None and reads.dispatcher is dispatcher:reads.discard(refs)
