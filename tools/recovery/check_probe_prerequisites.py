"""Real page/codec paths with scripted answers; no language quality claim."""
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence,Ground
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import choose,choose_domain,licensed
from ah.formalizer.probe_prerequisites import accepted
from ah.formalizer.partial_readings import valid_domain

release=SimpleNamespace(sha256='r',entries=lambda kind:[{'max_rule_steps':100}])
cfg={'max_candidates':8,'context_chars':2000}
class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,*answers):self.answers=iter(answers);self.prompts=[];self.hook=None
    def select(self,prompt):
        self.prompts.append(str(prompt))
        if self.hook:self.hook()
        return next(self.answers)
def fixture():
    s=t0('source');s.evidence=[TokenEvidence('source','t',0,6)]
    r=TextRegion('r','SENTENCE',(0,6),('t',),None)
    sel=Selector('1','1')
    first=choose(s,release,sel,r,cfg,'relative_argument_role',
        [{'candidate_id':'SUBJECT','label':'Subject of the description'}],'Which role?')
    return s,r,sel,first
def dependent(s,r,sel,first,**kw):
    return choose(s,release,sel,r,cfg,'relative_marker_reading',
        [{'candidate_id':'reading','label':'Reading compatible with the subject role'}],'Which reading?',
        prerequisites=(accepted('relative_argument_role',first),),**kw)
def retire(s,first):
    s.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':first[1]['decision_ref']})

s,r,sel,first=fixture();second=dependent(s,r,sel,first)
assert second and licensed(s,second[1])
assert 'Preserve this previously selected interpretation: Subject of the description' in sel.prompts[-1]
retire(s,first)
assert not licensed(s,second[1]),'dependent receipt must lose permission with its premise'
assert dependent(s,r,sel,first) is None and len(sel.prompts)==2,'cached answer cannot bypass premise checks'
# Empty enumeration must not establish a negative conclusion from a retired premise.
assert choose(s,release,sel,r,cfg,'relative_marker_reading',[],'Which reading?',
    empty={'candidate_id':'EMPTY','label':'No reading'},
    prerequisites=(accepted('relative_argument_role',first),)) is None
s,r,sel,first=fixture();premise=accepted('relative_argument_role',first)
premise.value['label']='Changed meaning'
assert premise.errors(s)==('PREMISE_PAYLOAD_CHANGED',)
assert accepted('structural_owner',first).errors(s)==('PREMISE_SLOT_MISMATCH',)
# A callback may revise state while the answer is being obtained.
s,r,sel,first=fixture();sel.hook=lambda:retire(s,first)
assert dependent(s,r,sel,first) is None
# Partial domains have the same dependency contract as single selections.
s,r,sel,first=fixture();sel.answers=iter(['1,2'])
domain=choose_domain(s,release,sel,r,cfg,'relative_marker_reading',
    [{'candidate_id':'a','label':'Reading A'},{'candidate_id':'b','label':'Reading B'}],
    'Which readings?',prerequisites=(accepted('relative_argument_role',first),))
assert domain and valid_domain(s,domain.record())
retire(s,first);assert not valid_domain(s,domain.record())
print('Prerequisites: prompt evidence, stale replay, payload/slot, in-call revision, empty and partial domains: PASS')

# Synthetic accepted receipts exercise dependency depth, not language parsing.
from copy import deepcopy
from ah.formalizer.canonical_ledger import digest
s,r,sel,first=fixture();previous=first
for i in range(1200):
    value={'candidate_id':str(i),'label':'Dependent interpretation '+str(i)}
    key='depth:'+str(i);proof={'decision_ref':key,'candidate_id':str(i),'domain_ref':key,'payload_hash':digest(value)}
    decision=deepcopy(s.decisions[first[1]['decision_ref']]);decision.frame_id=key;decision.selected=(str(i),);decision.candidates=(str(i),)
    decision.grounds=[Ground('D','synthetic depth witness',str(i))]
    s.decisions[key]=decision
    s.syntax_trace.append({'kind':'STRUCTURAL_TASK','decision_ref':key,'selected':str(i),
        'enumeration_complete':True,'payload_hash':digest(value),'alternatives':[value],
        'prerequisites':[accepted('relative_argument_role',previous).record()]})
    previous=(value,proof)
assert licensed(s,previous[1])
retire(s,first);assert not licensed(s,previous[1])
print('Dependency graph: 1200 accepted receipts without Python recursion; root retirement propagates: PASS')
