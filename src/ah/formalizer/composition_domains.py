"""Addressed finite domains and binary constraint propagation, without joins.

The engine knows no words or grammatical constructions. Callers supply typed
compatibility predicates; source/model decisions only restrict existing IDs.
Arc consistency does not claim to solve arbitrary global ambiguity.
"""
from collections import defaultdict, deque


class DomainNetwork:
    def __init__(self, domains):
        self.domains={name:dict(values) for name,values in domains.items()}
        self.neighbours=defaultdict(set)
        self.constraints=defaultdict(list)
        self.queue=deque()
        self.queued=set()
        self.removals=[]

    def _enqueue(self, left, right):
        edge=(left,right)
        if edge not in self.queued:
            self.queue.append(edge);self.queued.add(edge)

    def connect(self, left, right, compatible, reason):
        if left==right or left not in self.domains or right not in self.domains:
            raise ValueError('COMPOSITION_CONSTRAINT_ENDPOINT_INVALID')
        self.neighbours[left].add(right);self.neighbours[right].add(left)
        self.constraints[left,right].append((compatible,reason))
        self.constraints[right,left].append((lambda b,a:compatible(a,b),reason))
        self._enqueue(left,right);self._enqueue(right,left)

    def restrict(self, name, allowed, reason):
        allowed=set(allowed)
        removed=[cid for cid in self.domains[name] if cid not in allowed]
        if removed:
            for cid in removed:del self.domains[name][cid]
            self.removals.append({'variable_ref':name,'removed':removed,'reason':reason})
            for other in sorted(self.neighbours[name]):self._enqueue(other,name)
        return bool(self.domains[name])

    def copy(self):
        other=DomainNetwork(self.domains)
        other.neighbours=defaultdict(set,{k:set(v) for k,v in self.neighbours.items()})
        other.constraints=defaultdict(list,{k:list(v) for k,v in self.constraints.items()})
        other.queue=deque(self.queue);other.queued=set(self.queued)
        other.removals=list(self.removals)
        return other

    def propagate(self, spend=None):
        while self.queue:
            left,right=self.queue.popleft();self.queued.remove((left,right))
            checks=self.constraints[left,right]
            def compatible(a,b):
                if spend:spend()
                return all(check(a,b) for check,_ in checks)
            allowed=[cid for cid,a in self.domains[left].items()
                     if any(compatible(a,b)
                            for b in self.domains[right].values())]
            if not self.restrict(left,allowed,{'peer_ref':right,
                    'constraints':[reason for _,reason in checks]}):
                return False
        return all(self.domains.values())

    def snapshot(self):
        return {'domains':{name:list(values) for name,values in self.domains.items()},
                'constraints':[{'left':a,'right':b,'rules':[r for _,r in checks]}
                               for (a,b),checks in self.constraints.items() if a<b],
                'removals':list(self.removals)}
