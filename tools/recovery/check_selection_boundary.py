"""Controlled boundary diagnostics, not evidence of language-model quality."""
from copy import deepcopy
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.component_probe import _probe
from ah.formalizer.structural_tasks import choose,licensed
from ah.formalizer.selection_evidence import selected_candidate
from ah.formalizer.regions import TextRegion
from ah.formalizer.state import TokenEvidence

class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,*answers):self.answers=iter(answers);self.calls=0
    def select(self,prompt):self.calls+=1;return next(self.answers)

release=SimpleNamespace(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
options=[{'candidate_id':'a','label':'first','role':'SUBJECT'}, {'candidate_id':'b','label':'second','role':'OBJECT'}]
state=t0('source');state.evidence=[TokenEvidence('source','t',0,6)]
selector=Selector('1')
assert _probe(state,selector,release,'p','component_attachment',options,'source',(0,6),question='Which interpretation fits?',target_refs=('t',))=='a'
assert state.decisions['p'].outcome is None and state.decisions['p'].search_complete is False
state.decisions['p'].outcome='RESOLVED'
state.decisions['p'].history.append({'kind':'SEMANTIC_VALIDATION'})
assert _probe(state,selector,release,'p','component_attachment',options,'source',(0,6),question='Which interpretation fits?',target_refs=('t',))=='a'
assert state.decisions['p'].outcome is None and selector.calls==1
assert not any(h.get('kind')=='SEMANTIC_VALIDATION' for h in state.decisions['p'].history if isinstance(h,dict))
state.observation['clarification_choices']={'p':'a'}
state.budget.llm_limit=state.budget.llm_calls
assert _probe(state,selector,release,'p','component_attachment',options,'source',(0,6),question='Which interpretation fits?',target_refs=('t',))=='a'
assert selector.calls==1 and state.decisions['p'].outcome is None
state.budget.llm_limit=100
state.observation.pop('clarification_choices')
region=TextRegion('r','SENTENCE',(0,6),('t',),None)
cfg={'max_candidates':1,'context_chars':1000}
selector=Selector('1','0')
value,proof=choose(state,release,selector,region,cfg,'slot',options,'Which?')
assert selected_candidate(state.decisions[proof['decision_ref']])=='a'
assert state.decisions[proof['decision_ref']].outcome is None
assert licensed(state,proof,role='SUBJECT') and not licensed(state,proof,role='OBJECT')
again=choose(state,release,selector,region,cfg,'slot',options,'Which?')
assert again==(value,proof) and selector.calls==2
page=next(row['decision_ref'] for row in state.syntax_trace if row.get('kind')=='STRUCTURAL_TASK' and row.get('selected')=='a' and 'page' in row)
assert not state.decisions[page].search_complete
assert not state.component_probe_records[page]['decision']['search_complete']
for row in state.syntax_trace:
    if row.get('decision_ref')==proof['decision_ref'] and row.get('alternatives'):
        row['alternatives'][0]['role']='OBJECT'
assert not licensed(state,proof,role='OBJECT')
# Changing payload while retaining label/ID must ask again and invalidate the old proof.
changed=deepcopy(options);changed[0]['role']='RECIPIENT'
selector=Selector('1','0')
value2,proof2=choose(state,release,selector,region,cfg,'slot',changed,'Which?')
assert selector.calls==1 and proof2!=proof and licensed(state,proof2,role='RECIPIENT')
print('selection/readiness, replay, page/domain closure and payload mutation: PASS')
