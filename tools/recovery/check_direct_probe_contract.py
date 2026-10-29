"""Direct focus and legacy temporal-row compatibility, scripted responses."""
from types import SimpleNamespace
from dataclasses import replace
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence,FrameCandidate
from ah.formalizer.component_probe import _probe
from ah.formalizer.direct_probe_inputs import inputs

s=t0('там там');s.evidence=[TokenEvidence('там','a',0,3),TokenEvidence('там','b',4,7)]
release=SimpleNamespace(sha256='r',entries=lambda kind:[{'max_rule_steps':100}])
options=[{'candidate_id':'yes','label':'Proposed function'}]
seen=[];sel=SimpleNamespace(selection_reply_format='SELECT_LABELS_V1',select=lambda p:seen.append(str(p)) or '1')
assert _probe(s,sel,release,'missing','spatial_function',options,s.text,(0,7),question='Which function?') is None
assert not seen
assert _probe(s,sel,release,'present','spatial_function',options,s.text,(4,7),
    question='Which function in the reused content?',target_refs=('a',))=='yes'
assert 'Interpretation area: characters 4:7' in seen[-1] and '«там» at characters 0:3' in seen[-1]
task=inputs(s,'spatial_function',('a',),options,(0,7),'Which function?')
assert 'TARGET_VIEW_MISMATCH' in replace(task,descriptions=('wrong',)).errors(s,'spatial_function',options,(0,7))
assert 'CANDIDATE_PAYLOAD_CHANGED' in task.errors(s,'spatial_function',[{**options[0],'label':'Different meaning'}],(0,7))
assert _probe(s,sel,release,'wrong-family','predicate_value',options,s.text,(0,7),
    question='Which function?',inputs=task) is None
print('Direct contract: missing focus blocks, source/use ranges distinguished, payload/view guarded, semantic family cannot be bypassed: PASS')

from ah.formalizer.component_temporal_scope import resolve
from ah.formalizer.regions import TextRegion
import re
for answers,success in [('11',True),('12',False)]:
    s=t0('После дождя до дождя он идёт')
    s.evidence=[TokenEvidence(m.group(),str(i),m.start(),m.end()) for i,m in enumerate(re.finditer(r'\S+',s.text))]
    rows=[{'operator':op,'anchor_ref':ref,'anchor_surface':'дождя'} for op,ref in [('AFTER','1'),('BEFORE','3')]]
    f=FrameCandidate('f','FLAT','идёт',(),predicate_token_ref='5',source_range=(0,len(s.text)),semantic={'relative_temporal':rows})
    root=FrameCandidate('root','FLAT','идёт',(),predicate_token_ref='5',source_range=(0,len(s.text)))
    s.frames=[f,root];r=TextRegion('r','SENTENCE',(0,len(s.text)),tuple(t.token_id for t in s.evidence),None)
    replies=iter(answers);seen=[];sel.select=lambda p:seen.append(str(p)) or next(replies)
    assert resolve(s,release,sel,r,s.evidence,[f,root],{'context_chars':2000}) is success
    assert len(seen)==2 and '«дождя» @6:11' in seen[0] and '«дождя» @15:20' in seen[1]
    if success:assert len(root.semantic['relative_time_targets'])==2 and not f.semantic['relative_temporal']
    else:assert 'relative_time_targets' not in root.semantic and f.semantic['relative_temporal']==rows
print('Legacy temporal consumer: one independently addressed row per answer; mixed scope cannot transfer all rows or half-write: PASS')
