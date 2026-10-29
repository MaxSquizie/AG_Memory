"""Contract contrasts through the real selector/codec; no model-quality claim."""
from copy import deepcopy
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import choose, licensed
from ah.formalizer.task_contracts import SelectionReceipt, SelectionPurpose as Purpose, TaskOutcome

class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,*answers):self.answers=iter(answers);self.prompts=[]
    def select(self,prompt):self.prompts.append(str(prompt));return next(self.answers)

release=SimpleNamespace(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
region=TextRegion('r','SENTENCE',(0,6),('t',),None)
cfg={'max_candidates':1,'context_chars':2000}
options=[{'candidate_id':'a','label':'reading A'},{'candidate_id':'b','label':'reading B'}]
def state():
    s=t0('source');s.evidence=[TokenEvidence('source','t',0,6)];return s

# Exhausting a caller iterator is scoped negative evidence, not language closure.
r=SelectionReceipt(('a',),(),True)
assert r.outcome==TaskOutcome.GENERATOR_NONE_FIT
assert r.record()['enumeration_complete'] and not r.record()['interpretation_complete']
assert SelectionReceipt(('a',),(),False).outcome==TaskOutcome.INCOMPLETE
s=state();sel=Selector('0','0')
assert choose(s,release,sel,region,cfg,'custom',options,'Which?') is None
row=next(r for r in s.syntax_trace if r.get('kind')=='TASK_DOMAIN')
assert row['enumeration_scope']=='CALLER_GENERATOR' and row['task_outcome']==TaskOutcome.GENERATOR_NONE_FIT.value
assert not row['interpretation_complete'] and len(sel.prompts)==2
# Insufficient context on a later page cannot produce completion/EMPTY.
s=state();sel=Selector('0','?')
assert choose(s,release,sel,region,cfg,'custom',options,'Which?',empty={'candidate_id':'DONE','label':'finished'}) is None
assert not any(r.get('kind')=='TASK_DOMAIN' for r in s.syntax_trace)
# Same source/options/question with a different operation is a distinct task.
s=state();sel=Selector('1','1')
a=choose(s,release,sel,region,cfg,'custom',options[:1],'Which?')
b=choose(s,release,sel,region,cfg,'custom',options[:1],'Which?',purpose=Purpose.NEXT)
assert a[1]!=b[1] and len(sel.prompts)==2 and licensed(s,b[1])
assert 'alternative next steps' in sel.prompts[-1]
changed=deepcopy(b[1]);changed['selection_purpose']=Purpose.ALTERNATIVE.value
assert not licensed(s,changed)
# Multiple next steps remain alternatives; neither is consumed as a joint set.
s=state();sel=Selector('1,2')
assert choose(s,release,sel,region,{**cfg,'max_candidates':2},'custom',options,'Next?',purpose=Purpose.NEXT) is None
row=next(r for r in s.syntax_trace if r.get('kind')=='TASK_DOMAIN')
assert row['supported_ids']==['a','b'] and row['selection_purpose']==Purpose.NEXT.value
for invalid in [[],options]:
    s=state();sel=Selector()
    try:choose(s,release,sel,region,cfg,'custom',invalid,'Confirm?',purpose=Purpose.CONFIRM)
    except ValueError as e:assert str(e)=='CONFIRMATION_REQUIRES_ONE_PROPOSAL'
    else:raise AssertionError('invalid confirmation accepted')
    assert not sel.prompts
s=state();sel=Selector('0')
assert choose(s,release,sel,region,cfg,'custom',options[:1],'Confirm?',purpose=Purpose.CONFIRM) is None
row=next(r for r in s.syntax_trace if r.get('kind')=='TASK_DOMAIN')
assert row['candidate_ids']==['a'] and row['selection_purpose']==Purpose.CONFIRM.value
print('F05/F06: scoped exhaustion, unknown page, distinct operation/cache/proof, alternative next steps and one-proposal confirmation: PASS')

# A caller cannot silently downgrade a collecting consumer, even with no options.
for slot in ['nominal_function','temporal_function','structural_function_owner','structural_partition']:
    s=state();sel=Selector()
    try:choose(s,release,sel,region,cfg,slot,[],'Which?',empty={'candidate_id':'DONE','label':'done'})
    except ValueError as e:assert str(e)=='SELECTION_PURPOSE_CONSUMER_MISMATCH'
    else:raise AssertionError('consumer type bypass')
    assert not sel.prompts
print('Declared collecting/confirmation consumers reject mismatched operation before empty completion: PASS')
