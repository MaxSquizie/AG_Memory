"""Final requests for selected-structure families, with scripted answers."""
from dataclasses import replace
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence,FrameCandidate
from ah.formalizer.component_probe import _probe
from ah.formalizer.reference_structure import focus_inputs
from ah.formalizer.probe_inputs import FOCUS_FAMILIES

s=t0('Иван не пришёл')
s.evidence=[TokenEvidence('Иван','a',0,4),TokenEvidence('не','n',5,7),TokenEvidence('пришёл','p',8,14)]
s.frames=[FrameCandidate('f','FLAT','пришёл',(),predicate_token_ref='p',argument_token_refs=('a',),
    source_range=(0,14),semantic={'proposed_roles':{'a':'SUBJECT'}})]
s.logical_roots=[{'operator':'NOT','operands':[{'frame_ref':'f'}],'anchor_refs':['n']}]
s.structural_closed=True
release=SimpleNamespace(sha256='r');options=[{'candidate_id':'one','label':'Proposed reading'}]
seen=[];selector=SimpleNamespace(selection_reply_format='SELECT_LABELS_V1',select=lambda p:seen.append(str(p)) or '1')
for slot in FOCUS_FAMILIES:
    task=focus_inputs(s,slot,('p',),options)
    assert _probe(s,selector,release,slot,slot,options,s.text,(0,14),question='Resolve this question.',inputs=task)=='one'
    assert '«пришёл» at characters 8:14' in seen[-1] and 'negation of' in seen[-1]
    assert '«Иван» at characters 0:4' in seen[-1]
    count=len(seen)
    assert _probe(s,selector,release,slot,slot,options,s.text,(0,14),question='Resolve this question.') is None
    assert len(seen)==count
    bad=replace(task,target_descriptions=('wrong target',))
    assert 'TARGET_VIEW_MISMATCH' in bad.errors(s,slot,options,(0,14))
    s.frames[0].semantic['proposed_roles']['a']='OBJECT'
    assert 'STRUCTURE_CHANGED' in task.errors(s,slot,options,(0,14))
    s.frames[0].semantic['proposed_roles']['a']='SUBJECT'
s.structural_closed=False
assert 'STRUCTURE_NOT_SEALED' in focus_inputs(s,'predicate_value',('p',),options).missing
assert 'STRUCTURE_NOT_SEALED' not in focus_inputs(s,'speech_act',('p',),options,
    trees=s.logical_roots,require_sealed=False).missing
print('Five selected-structure families: exact target/roles/NOT in final prompt, missing contract, stale structure, pre/post-seal distinction: PASS')

s.structural_closed=True
task=focus_inputs(s,'predicate_value',('p',),options)
def revise_during_answer(prompt):
    s.frames[0].semantic['proposed_roles']['a']='OBJECT'
    return '1'
changing=SimpleNamespace(selection_reply_format='SELECT_LABELS_V1',select=revise_during_answer)
assert _probe(s,changing,release,'in-call','predicate_value',options,s.text,(0,14),
    question='Which lexical use?',inputs=task) is None
assert not s.decisions['in-call'].selected and s.decisions['in-call'].outcome=='UNRESOLVED'
s.frames[0].semantic['proposed_roles']['a']='SUBJECT';s.structural_closed=False
print('Direct probe: an in-call structural revision invalidates the returned selection and cached decision: PASS')

from ah.formalizer.regions import TextRegion
from ah.formalizer.scope_assignment import assign
from ah.formalizer.probe_wording import frame_label
r=TextRegion('r','SENTENCE',(0,14),('a','n','p'),None)
release.entries=lambda kind:[{'max_rule_steps':100}]
modifier={'id':'m','label':'negation «не» @5:7'}
count=len(seen)
assert assign(s,release,selector,r,{'frame_ref':'f'},[modifier],{'max_candidates':8},node_labels={}) is None
assert len(seen)==count
assert assign(s,release,selector,r,{'frame_ref':'f'},[modifier],{'max_candidates':8},
    node_labels={'f':frame_label(s,s.frames[0])}) is not None
assert 'Target modifier: negation «не» @5:7' in seen[-1] and 'characters 8:14' in seen[-1]
print('Scope: absent source label blocks; real question identifies modifier and exact local target: PASS')

# Actual discourse producer: identical names remain separate source occurrences.
from ah.formalizer.state import MorphVariant
from ah.formalizer.discourse_scopes import prepare
import re
s=t0('Иван Иван сказал ты идёшь')
s.evidence=[TokenEvidence(m.group(),str(i),m.start(),m.end()) for i,m in enumerate(re.finditer(r'\S+',s.text))]
s.evidence[3].variants=(MorphVariant('ты','NPRO',person='2nd'),)
parent=FrameCandidate('parent','FLAT','сказал',(),predicate_token_ref='2',argument_token_refs=('0','1'),
    source_range=(0,len(s.text)),semantic={'proposed_roles':{'0':'SUBJECT','1':'RECIPIENT'},
        'proposition_args':{'OBJECT':{'tree':{'frame_ref':'child'},'attitude':'QUOTED','holder_role':'SUBJECT'}}})
child=FrameCandidate('child','FLAT','идёшь',(),predicate_token_ref='4',argument_token_refs=('3',),
    source_range=(17,len(s.text)),semantic={'proposed_roles':{'3':'SUBJECT'},'component_child':'parent'})
s.frames=[parent,child];replies=iter(['1','3']);seen=[]
selector.select=lambda prompt:seen.append(str(prompt)) or next(replies)
prepare(s,release,selector)
assert child.semantic['discourse_scope']['addressee_mention']=='1'
assert 'characters 0:4' in seen[-1] and 'characters 5:9' in seen[-1]
assert 'Established speaker: «Иван» @0' in seen[-1]
print('Actual discourse producer: same-name addressee candidates distinguished; selected owner and speaker retained: PASS')
