"""Dispatcher subscriptions to real proofs; authored replies, no live LLM."""
from types import SimpleNamespace as NS
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import choose,licensed
from ah.formalizer.component_probe_replay import supersede
from ah.formalizer.composition_dispatcher import Dispatcher,DispatchBlocked

s=t0('source');s.evidence=[TokenEvidence('source','t',0,6)]
r=TextRegion('r','SENTENCE',(0,6),('t',),None)
release=NS(sha256='release',entries=lambda k:[{'max_rule_steps':100}])
sel=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:'1')
value,proof=choose(s,release,sel,r,{'max_candidates':8,'context_chars':2000},'custom',[{'candidate_id':'x','label':'reading'}],'Which?')
d=Dispatcher(s);calls=[]
with patch('ah.formalizer.composition_session.current',return_value=NS(state=s,dispatcher=d)):
    def child():
        calls.append('child')
        return 'usable' if licensed(s,proof) else None
    def parent():return d.run('child',[],child,kind='GRAMMAR')
    assert d.run('parent',[],parent,kind='GRAMMAR')=='usable'
    assert d.run('parent',[],parent,kind='GRAMMAR')=='usable' and calls==['child']
    assert d.run('independent',[],lambda:'independent',kind='GRAMMAR')=='independent'
    supersede(s,proof['decision_ref'],'replacement')
    assert not d.valid('child') and not d.valid('parent') and d.valid('independent')
    assert d.run('parent',[],parent,kind='GRAMMAR') is None and calls==['child','child']
# Invalidation issued during computation must not be erased by publishing it.
d=Dispatcher(s);calls=[]
def compute():
    calls.append(1)
    if len(calls)==1:d.invalidate('task','external change')
    return len(calls)
assert d.run('task',[],compute,kind='GRAMMAR')==2
# Repeated unchanged invalidation terminates rather than looping or publishing.
d=Dispatcher(s)
def unstable():d.invalidate('task','unchanged conflict');return 'stale'
try:d.run('task',[],unstable,kind='GRAMMAR')
except DispatchBlocked as e:assert str(e)=='COMPOSITION_DEPENDENCY_NO_PROGRESS'
else:raise AssertionError('unstable output published')
# Deep dependency validation does not depend on Python recursion depth.
d=Dispatcher(s)
for i in range(1500):
    d.nodes[str(i)]={'kind':'GRAMMAR','dirty':False,'revision':1,'result':i,
                    'reads':{str(i-1):1} if i else {},'evidence_reads':{}}
assert d.valid('1499');d.nodes['0']['dirty']=True;assert not d.valid('1499')
print('Dispatcher: proof subscriptions, unchanged reuse, transitive stale reads, independent branch, in-flight invalidation and deep graph: PASS')

# Absence is a read, too: a previously missing inventory becomes available.
from ah.formalizer import function_inventory as inv
s=t0('source');s.evidence=[TokenEvidence('source','t',0,6)];d=Dispatcher(s)
runtime=NS(state=s,dispatcher=d,input_signature=lambda:None,context_signature=lambda:None,domain_feedback=None)
with patch('ah.formalizer.composition_session.current',return_value=runtime):
    def available():return inv.current(s,'TEMPORAL',[]) is not None
    assert d.run('inventory-consumer',[],available,kind='GRAMMAR') is False
    assert inv.complete(s,inv.begin(s,'TEMPORAL',[]))
    assert not d.valid('inventory-consumer')
    assert d.run('inventory-consumer',[],available,kind='GRAMMAR') is True
print('Dispatcher: cached missing inventory is invalidated by a newly available receipt: PASS')
