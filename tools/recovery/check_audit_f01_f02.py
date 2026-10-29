"""Controlled contract checks, not a live model or end-to-end language test."""
from types import SimpleNamespace
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.component_nominal_questions import choose
from ah.formalizer.component_nominal_groups import select
from ah.formalizer.component_coordination import coordinate
from ah.formalizer.selection_evidence import selected_candidate

class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self, answer):self.answer=answer;self.calls=0
    def select(self, prompt):self.calls+=1;return self.answer

release=SimpleNamespace(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
cfg={'max_candidates':8,'context_chars':1000,'coordination_operators':['AND']}
def setup():
    state=t0('Иван и Пётр')
    state.evidence=[TokenEvidence('Иван','a',0,4),TokenEvidence('и','c',5,6),TokenEvidence('Пётр','b',7,11)]
    region=TextRegion('r','SENTENCE',(0,11),('a','c','b'),None)
    return state,region

for answer,expected in [('1','candidate'),('0',None),('?',None)]:
    state,region=setup();selector=Selector(answer)
    value=choose(state,release,selector,region,'unit',[{'candidate_id':'candidate','label':'Proposed reading'}],'Does this reading fit?')
    assert value==expected and selector.calls==1
    assert len(state.decisions)==1
    decision=next(iter(state.decisions.values()))
    assert selected_candidate(decision)==expected

# Fix the proposed domain only; run the real question, codec and consumer.
from ah.formalizer.state import MorphVariant
variant=MorphVariant('test','NOUN',cases=frozenset({'nomn'}))
for answer,expected in [('1','SUPPORTED'),('2','NOT_APPLICABLE'),('0','PENDING'),('?','PENDING')]:
    state,region=setup();selector=Selector(answer)
    for token in (state.evidence[0],state.evidence[2]):token.variants=(variant,)
    with patch('ah.formalizer.component_nominal_groups.connectives',return_value=[(5,6)]):
        result=select(state,release,selector,region,state.evidence,cfg)
    assert state.syntax_trace[-1]['task_outcome']==expected
    if expected=='NOT_APPLICABLE':assert result is None
    elif expected=='PENDING':assert result is False
    else:assert result and result[0]['member_refs']==['a','b']

# Rejection/uncertainty about the clause split must stop BEFORE child creation.
for answer in ('0','?'):
    state,region=setup();selector=Selector(answer)
    def forbidden(*args):raise AssertionError('unlicensed child composition')
    with patch('ah.formalizer.component_area_scope.allowed',return_value=True), patch('ah.formalizer.component_area_scope.connectives',return_value=[(5,6)]):
        result=coordinate(state,release,selector,region,state.evidence,[],cfg,[],compose_child=forbidden)
    assert result==[] and selector.calls==1
print('F01 singleton accepts/rejects/defers; F02 applicability and unlicensed split: PASS')

# Accepted source split may compose; retiring it during recursion forbids AND.
from ah.formalizer.component_probe_replay import supersede
for retire in (False,True):
    state,region=setup();selector=Selector('1')
    state.region_forest=SimpleNamespace(regions=[region])
    def child(child_region, tokens):
        if retire:
            proof=next(r['proof'] for r in state.syntax_trace if r.get('kind')=='COORDINATION_SOURCE_PARTITION')
            domain=next(r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==proof['domain_ref'])
            supersede(state,domain['page_refs'][0],'replacement')
        return [SimpleNamespace(frame_id=child_region.region_id,semantic={'structural_unresolved':False})]
    with patch('ah.formalizer.component_area_scope.allowed',return_value=True), patch('ah.formalizer.component_area_scope.connectives',return_value=[(5,6)]), patch('ah.formalizer.composition_children.select_child',side_effect=lambda s,r,sel,reg,frames,*args:frames[0]), patch('ah.formalizer.coordination_assignment.compose',return_value={'operator':'AND'}) as compose:
        result=coordinate(state,release,selector,region,state.evidence,[],cfg,[],compose_child=child)
    assert len(result)==2
    assert compose.call_count==(0 if retire else 1)
    assert all(f.semantic['structural_unresolved']==retire for f in result)
print('F02 confirmed split composes; proof retirement during child recursion blocks AND: PASS')
