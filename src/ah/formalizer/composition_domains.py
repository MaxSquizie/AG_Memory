"""Addressed finite domains and binary constraint propagation, without joins.

The engine knows no words or grammatical constructions. Callers supply typed
compatibility predicates; source/model decisions only restrict existing IDs.
Arc consistency does not claim to solve arbitrary global ambiguity.
"""
from collections import defaultdict, deque


class DomainNetwork:
    def __init__(self, domains, *, open_domains=()):
        self.domains={name:dict(values) for name,values in domains.items()}
        self.candidates={name:dict(values) for name,values in domains.items()}
        self.open_domains=set(open_domains)
        if not self.open_domains<=self.domains.keys():raise ValueError('COMPOSITION_OPEN_DOMAIN_UNKNOWN')
        self.obligations={}
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

    def restrict(self, name, allowed, reason, *, observed_only=False):
        if not observed_only and name in self.open_domains:
            self.open_domains.remove(name)
            for other in sorted(self.neighbours[name]):self._enqueue(other,name)
        allowed=set(allowed)
        removed=[cid for cid in self.domains[name] if cid not in allowed]
        if removed:
            for cid in removed:del self.domains[name][cid]
            self.removals.append({'variable_ref':name,'removed':removed,'reason':reason})
            for other in sorted(self.neighbours[name]):self._enqueue(other,name)
        return bool(self.domains[name])

    def copy(self):
        other=DomainNetwork(self.domains,open_domains=self.open_domains)
        other.candidates={k:dict(v) for k,v in self.candidates.items()}
        other.neighbours=defaultdict(set,{k:set(v) for k,v in self.neighbours.items()})
        other.constraints=defaultdict(list,{k:list(v) for k,v in self.constraints.items()})
        other.queue=deque(self.queue);other.queued=set(self.queued)
        other.removals=list(self.removals)
        other.obligations={edge:list(rows) for edge,rows in self.obligations.items()}
        return other

    def extend(self, name, values, *, complete=False):
        """Only an explicitly open source can grow without rebuilding proofs."""
        if name not in self.open_domains:raise ValueError('COMPOSITION_DOMAIN_ALREADY_CLOSED')
        for cid,value in values.items():
            if cid in self.candidates[name] and self.candidates[name][cid]!=value:
                raise ValueError('COMPOSITION_CANDIDATE_ID_CHANGED')
        # Repeated pages cannot resurrect candidates already disproved.
        self.domains[name].update({cid:value for cid,value in values.items() if cid not in self.candidates[name]})
        self.candidates[name].update(values)
        if complete:self.open_domains.remove(name)
        for other in sorted(self.neighbours[name]):
            self._enqueue(name,other);self._enqueue(other,name)

    def propagate(self, spend=None):
        while self.queue:
            # Keep the edge queued until its entire revision succeeds. A fuel
            # exception must not turn an unfinished check into a fixed point.
            left,right=self.queue[0]
            checks=self.constraints[left,right]
            def compatible(a,b):
                if spend:spend()
                unknown=False
                for check,_ in checks:
                    result=check(a,b)
                    if result is False:return False
                    if result is None:unknown=True
                    elif result is not True:raise ValueError('COMPOSITION_CONSTRAINT_RESULT_INVALID')
                return None if unknown else True
            allowed=[];pending=[]
            for cid,a in self.domains[left].items():
                supported=False;unknown=False
                for b in self.domains[right].values():
                    result=compatible(a,b)
                    if result is True:supported=True;break
                    unknown |= result is None
                if supported or unknown or right in self.open_domains:allowed.append(cid)
                if not supported and (unknown or right in self.open_domains):
                    pending.append({'candidate_ref':cid,'reason':
                        'PEER_SOURCE_OPEN' if right in self.open_domains else 'COMPATIBILITY_UNKNOWN'})
            self.queue.popleft();self.queued.remove((left,right))
            self.obligations[left,right]=pending
            if not self.restrict(left,allowed,{'peer_ref':right,
                    'constraints':[reason for _,reason in checks]},observed_only=True):
                if left not in self.open_domains:return False
        return all(values or name in self.open_domains for name,values in self.domains.items())

    def snapshot(self):
        return {'domains':{name:list(values) for name,values in self.domains.items()},
                'constraints':[{'left':a,'right':b,'rules':[r for _,r in checks]}
                               for (a,b),checks in self.constraints.items() if a<b],
                'removals':list(self.removals),
                'open_domains':sorted(self.open_domains),
                'pending_edges':[list(edge) for edge in self.queue],
                'obligations':[{'left':a,'right':b,**row}
                               for (a,b),rows in self.obligations.items() for row in rows
                               if row['candidate_ref'] in self.domains[a]],
                'propagation_complete':not self.queue}
