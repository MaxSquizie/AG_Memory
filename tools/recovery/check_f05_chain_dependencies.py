"""Finite dependency graph properties, independent of model answers."""
from ah.formalizer.pipeline import t0
from ah.formalizer.nominal_reference_chain import finish
from ah.formalizer.canonical_ledger import CanonicalLedger


def pending(mention,parent):
    return ({'interpretation_decision_ref':mention+'|referent'},
            {'mention_ref':parent,'decision_ref':parent+'|referent'})
s=t0('источник')
s.observation['nominal_reference_bindings']={'root':{'target_ref':'K:root','reference_kind':'GROUP',
    'member_refs':['M:a','M:b'],'premise_support_refs':['support']}}
# Dependents arrive before parents; no recursion or arbitrary depth cutoff.
count=1200
work={str(i):pending(str(i),str(i-1) if i else 'root') for i in reversed(range(count))}
assert not finish(s,work)
last=s.observation['nominal_reference_bindings'][str(count-1)]
assert last['target_ref']=='K:root' and last['member_refs']==['M:a','M:b']
work={'a':pending('a','b'),'b':pending('b','a'),'c':pending('c','a'),
      'missing':pending('missing','unavailable'),'ok':pending('ok','root')}
assert finish(s,work)=={'a','b','c','missing'}
assert 'ok' in s.observation['nominal_reference_bindings']
assert s.has_diag('NOMINAL_REFERENCE_DEPENDENCY_CYCLE') and s.has_diag('NOMINAL_REFERENCE_DEPENDENCY_UNRESOLVED')
assert all(x not in s.observation['nominal_reference_bindings'] for x in ['a','b','c','missing'])
# Durable reference graph: deep chain, shared DAG join, root retirement, cycles.
ledger=CanonicalLedger();bindings=ledger.data['bindings']
bindings['root']={'status':'LIVE','target_ref':'M:x'}
for i in range(1600):
    bindings[str(i)]={'status':'LIVE','binding_kind':'NOMINAL_REFERENCE','target_ref':'M:x',
                      'anchor_binding_ref':str(i-1) if i else 'root'}
assert ledger.binding_live('1599',set())
bindings['group']={'status':'LIVE','binding_kind':'NOMINAL_GROUP_ANCHOR','member_binding_refs':['1599','800']}
assert ledger.binding_live('group',set()),'shared dependency is not a cycle'
bindings['root']['status']='RETRACTED'
assert not ledger.binding_live('1599',set()) and not ledger.binding_live('group',set())
bindings['root']={'status':'LIVE','target_ref':'M:x','binding_kind':'NOMINAL_REFERENCE','anchor_binding_ref':'1599'}
assert not ledger.binding_live('1599',set())
bindings['self']={'status':'LIVE','target_ref':'M:x','binding_kind':'NOMINAL_REFERENCE','anchor_binding_ref':'self'}
assert not ledger.binding_live('self',set())
print('PASS: 1200 source dependencies, K type preservation, unresolved cycles/missing parents, 1600 durable links, DAG join, root retirement and cycles')
