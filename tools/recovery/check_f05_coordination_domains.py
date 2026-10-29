"""Exhaustive small-domain pruning oracle and actual dependency-network contrasts."""
from itertools import product,permutations,combinations
from copy import deepcopy
from unittest.mock import patch
from ah.formalizer.component_nominal_groups import compatible_cases,merge_groups,select
from ah.formalizer.dependency_constraints import network
from ah.formalizer.state import MorphVariant,TokenEvidence
from ah.formalizer.pipeline import t0
from ah.formalizer.regions import TextRegion

universe={'nom','acc','dat'}
domains=[None,*[set(v) for n in range(1,4) for v in combinations(sorted(universe),n)]]
# Independent oracle: an assignment exists iff one case satisfies all members.
for ds in product(domains,repeat=3):
    readings=[{'cases':sorted(d) if d is not None else [],'origin':'CONTEXTUAL' if d is None else 'DICTIONARY'} for d in ds]
    possible=any(all(d is None or case in d for d in ds) for case in universe)
    assert compatible_cases(readings)==possible,(ds,possible)
    for group in domains:
        possible=any((group is None or case in group) and all(d is None or case in d for d in ds) for case in universe)
        assert compatible_cases(readings,group)==possible
assert not compatible_cases([{'cases':[],'origin':'PREDICTED'}])
assert not compatible_cases([{'cases':[],'origin':'DICTIONARY'}])

def edge(a,b,cases):return {'member_refs':[a,b],'marker_refs':[a+b],'cases':cases,'operator':'AND','contextual_readings':[]}
edges=[edge('a','b',['nom']),edge('c','d',None),edge('b','c',['nom','acc'])]
original=deepcopy(edges)
for order in permutations(edges):
    groups=merge_groups(order)
    assert len(groups)==1 and set(groups[0]['member_refs'])==set('abcd') and groups[0]['cases']==['nom']
assert edges==original
assert merge_groups([edge('a','b',['nom']),edge('b','c',['acc'])]) is None

def root(cases,origin='DICTIONARY'):
    return {'kind':'ROOT','role':'subject','morph':{'cases':cases,'pos':'NOUN','origin':origin}}
pool={'a':{'x':root([], 'CONTEXTUAL')},'b':{'y':root(['nom'])}}
group=[edge('a','b',['nom'])]
g=network(pool,group);assert g.propagate() and all(g.domains.values())
g=network(pool);assert not g.propagate()  # two ungrouped participants cannot occupy one single slot
bad={'a':{'x':root(['acc'])},'b':{'y':root(['nom'])}}
assert not network(bad,group).propagate()
# Producer preserves explicitly contextual unknownness; it creates no case fact.
s=t0('шмырлик и кот')
tokens=[TokenEvidence('шмырлик','a',0,7,variants=(MorphVariant(None,'NOUN',origin='CONTEXTUAL'),)),
        TokenEvidence('и','and',8,9),TokenEvidence('кот','b',10,13,variants=(MorphVariant('кот','NOUN',frozenset({'nom'}),origin='DICTIONARY'),))]
r=TextRegion('r','SENTENCE',(0,13),('a','and','b'),None)
with patch('ah.formalizer.component_nominal_groups.connectives',return_value=[(8,9)]),patch('ah.formalizer.component_nominal_groups._probe',return_value='NOMINAL'):
    result=select(s,None,None,r,tokens,{'max_candidates':8,'context_chars':100})
assert result[0]['cases']==['nom'] and not tokens[0].variants[0].cases
print('F05 coordination: exhaustive finite case-domain oracle, connected-group permutations, actual dependency propagation, unknown preserved and conflicts rejected: PASS')
