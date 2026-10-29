"""Page-boundary diagnostics with real choose/codec and scripted responses."""
from types import SimpleNamespace
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import choose, licensed
from ah.formalizer.structural_probe_inputs import inputs
from ah.formalizer.component_probe import _probe

release=SimpleNamespace(sha256='r',entries=lambda kind:[{'max_rule_steps':100}])
cfg={'max_candidates':1,'context_chars':1000}
options=[{'candidate_id':'a','label':'First interpretation','meaning':'first'},
         {'candidate_id':'b','label':'Second interpretation','meaning':'second'}]
class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,*answers):self.answers=iter(answers);self.calls=0
    def select(self,prompt):self.calls+=1;return next(self.answers)
def fixture():
    s=t0('source');s.evidence=[TokenEvidence('source','t',0,6)]
    return s,TextRegion('r','SENTENCE',(0,6),('t',),None)

s,region=fixture();selector=Selector('0','1')
value,proof=choose(s,release,selector,region,cfg,'role',options,'Which interpretation fits?')
assert value['candidate_id']=='b' and licensed(s,proof,meaning='second')
contracts=[r for r in s.syntax_trace if r.get('kind')=='PROBE_INPUT_CONTRACT']
assert len(contracts)==2 and all(r['status']=='PAGE_DECLARED' for r in contracts)
assert [r['inputs']['page'] for r in contracts]==[0,1]
assert all(r['inputs']['negative_scope']=='DISPLAYED_PAGE' for r in contracts)
s,region=fixture();selector=Selector('?')
assert choose(s,release,selector,region,cfg,'role',options,'Which interpretation fits?') is None
assert selector.calls==1
s,region=fixture();selector=Selector('1')
task=inputs(s,region,'role',options[:1],'Which?','source',0)
choices=[{k:v[k] for k in ('candidate_id','label')} for v in options[:1]]
assert not task.errors(s,'role',choices,(0,6))
# A different question must not borrow an otherwise identical declaration.
assert _probe(s,selector,release,'p','role',choices,'source',(0,6),question='Different?',inputs=task) is None
assert selector.calls==0
assert 'PAGE_DOMAIN_MISMATCH' in task.errors(s,'role',[{'candidate_id':'b','label':'Second'}],(0,6))
s.evidence[0].span='changed'
assert 'SOURCE_CHANGED' in task.errors(s,'role',choices,(0,6))
with patch('ah.formalizer.composition_session.current',return_value=SimpleNamespace(input_signature=lambda:'new-parent')):
    assert 'PARENT_CONSTRAINT_CHANGED' in task.errors(s,'role',choices,(0,6))
print('F04 page rejection/unknown, declaration coverage, target/domain/question/source/parent guards: PASS')

from ah.formalizer.structural_tasks import source_set
from ah.formalizer.structural_probe_inputs import collection
s=t0('а а а');s.evidence=[TokenEvidence('а',ref,i,i+1) for ref,i in [('a',0),('b',2),('c',4)]]
region=TextRegion('r','SENTENCE',(0,5),('a','b','c'),None)
selector=Selector('1','1','2','1','0')
selected,proofs=source_set(s,release,selector,region,s.evidence,
    {'max_candidates':8,'context_chars':1000},'part','Select the words of this expression.')
assert [t.token_id for t in selected]==['a','c'] and all(licensed(s,p) for p in proofs)
records=[r['inputs']['source_selection'] for r in s.syntax_trace if r.get('kind')=='PROBE_INPUT_CONTRACT']
assert [r['operation'] for r in records]==['START','END','CONTINUE','PIECE_END','CONTINUE']
assert records[-1]['selected_refs']==('a','c')
assert 'characters 0:1' in s.decisions[next(r['decision_ref'] for r in reversed(s.syntax_trace) if r.get('kind')=='PROBE_INPUT_CONTRACT')].last_prompt
scope=collection('END',s.evidence,exclude=('b',),start='a')
assert 'SOURCE_INTERVAL_OUTSIDE_DOMAIN' in scope.errors(s,[{'token_ref':'c'}],region.token_refs)
scope=collection('CONTINUE',s.evidence,selected=(s.evidence[0],))
assert 'SOURCE_CANDIDATE_OUTSIDE_DOMAIN' in scope.errors(s,[{'token_ref':'a'}],region.token_refs)
print('F04 source collection: discontinuous selection, occurrence identity, no re-selection/crossing exclusion: PASS')
from ah.formalizer.task_contracts import SelectionPurpose
bad=collection('CONTINUE',s.evidence,selected=(s.evidence[0],),exclude=('a',))
assert choose(s,release,Selector(),region,cfg,'part',[],'Continue?',
    empty={'candidate_id':'DONE','label':'complete'},source_selection=bad,
    purpose=SelectionPurpose.NEXT) is None
assert s.syntax_trace[-1]['reason']=='SOURCE_CONTRACT_INVALID'
print('F04 empty generator cannot bypass contradictory source obligations: PASS')
scope=collection('END',s.evidence,start='a')
assert 'SOURCE_BOUNDARY_PAYLOAD_MISMATCH' in scope.errors(s,[{'token_ref':'c','index':1}],region.token_refs)
print('F04 displayed endpoint cannot license a different consumer slice index: PASS')
