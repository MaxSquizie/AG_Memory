"""Finite host-domain oracle; no model or native-write claim."""
from itertools import product,combinations
from types import SimpleNamespace as NS
from copy import deepcopy
from ah.formalizer.state import MorphVariant,TokenEvidence
from ah.formalizer.refinement_boundaries import agreeing
from ah.formalizer.refinement_group_hosts import candidates
universe={'nom','acc','dat'}
domains=[None,*[set(v) for n in range(1,4) for v in combinations(sorted(universe),n)]]
def reading(pos,domain):
    return MorphVariant(None,pos,frozenset(domain or ()),number='plur',
                        origin='CONTEXTUAL' if domain is None else 'DICTIONARY')
for left,right in product(domains,repeat=2):
    possible=any((left is None or c in left) and (right is None or c in right) for c in universe)
    assert agreeing(reading('NOUN',left),reading('PRTF',right))==possible
assert not agreeing(MorphVariant(None,'NOUN',origin='PREDICTED'),reading('PRTF',{'nom'}))
assert not agreeing(MorphVariant(None,'NOUN',frozenset({'nom'}),number='sing'),reading('PRTF',{'nom'}))

def binding(domain):
    return {'cases':sorted(domain or ()), 'origin':'CONTEXTUAL' if domain is None else 'DICTIONARY'}
for left,right,part in product(domains,repeat=3):
    group={'member_refs':['a','b'],'marker_refs':[],'operator':'AND'}
    frame=NS(semantic={'nominal_groups':[group],'morph_bindings':{'a':binding(left),'b':binding(right)},
                      'lexical_units':{'a':{'head_ref':'a'},'b':{'head_ref':'b'}}})
    evidence={'a':TokenEvidence('a','a',10,11),'b':TokenEvidence('b','b',20,21)}
    body=[TokenEvidence('description','d',0,5,variants=(reading('PRTF',part),))]
    original=deepcopy(frame.semantic)
    possible=any(all(d is None or c in d for d in [left,right,part]) for c in universe)
    rows=candidates([frame],evidence,body,all_hosts=True)
    assert bool(rows)==possible,(left,right,part)
    assert not candidates([frame],evidence,body)  # legacy postnominal contract remains bounded
    assert frame.semantic==original
    if left is None and right is None and rows:
        assert not next(iter(rows.values()))[2].cases  # no invented case fact
print('PASS: finite host/group case oracle, preposed description, known conflicts, unknown preservation, no mutation')
