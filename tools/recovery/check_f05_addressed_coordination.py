"""Real addressed collection/codec; no live model and no end-to-end write claim."""
from types import SimpleNamespace as NS
from copy import deepcopy
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.nominal_coordination_source import live
from ah.formalizer.component_nominal_groups import select
from ah.formalizer.component_probe_replay import supersede
from ah.formalizer.function_inventory import frame_live
release=NS(sha256='release',entries=lambda kind:[] if kind=='ScopeLexicon' else [{'max_rule_steps':100,'composition':{'structural_tasks':'CLOSED_RELATIONS_V1'}}])
cfg={'max_candidates':20,'context_chars':4000}
def run(words,answers):
    s=t0(' '.join(words));s.budget.llm_limit=100;s.evidence=[];offset=0
    for i,word in enumerate(words):
        s.evidence.append(TokenEvidence(word,str(i),offset,offset+len(word)))
        offset+=len(word)+1
    r=TextRegion('r','SENTENCE',(0,len(s.text)),tuple(t.token_id for t in s.evidence),None)
    replies=iter(answers);prompts=[]
    def reply(prompt):prompts.append(prompt);return next(replies)
    selector=NS(selection_reply_format='SELECT_LABELS_V1',select=reply)
    marker=s.evidence[2]
    result=select(s,release,selector,r,s.evidence,cfg)
    unused=list(replies)
    assert not unused,(unused,[(x.get('slot'),x.get('status'),x.get('reason')) for x in s.syntax_trace],s.diagnostics)
    return s,result,prompts
# Modifier between the first head and connector; three members, no POS filter.
s,groups,prompts=run(['Шмырлик','зелёный','и','Шмырлик','Пётр'],['1','1','1','3','2','0','1','2','1','0','0'])
assert groups[0]['member_refs']==['0','3','4'] and groups[0]['marker_refs']==['2']
assert groups[0]['cases'] is None and live(s,groups[0])
assert not any(t.variants for t in s.evidence)
frame=NS(semantic={'nominal_groups':deepcopy(groups)})
assert frame_live(s,frame)
changed=deepcopy(groups[0]);changed['member_refs'].append('1');assert not live(s,changed)
changed=deepcopy(groups[0]);changed['marker_refs']=[];assert not live(s,changed)
changed=deepcopy(groups[0]);changed.pop('coordination_completion');assert not live(s,changed)
proof=groups[0]['source_evidence'][0]['collection']['completion_proof']
supersede(s,proof['decision_ref'],'replacement')
assert not live(s,groups[0]) and not frame_live(s,frame)
# Explicit other scope and unknown have different control outcomes.
s,groups,_=run(['Иван','старший','и','Пётр'],['0']);assert groups==[]
s,groups,_=run(['Иван','старший','и','Пётр'],['2']);assert groups is False
assert any(d.code=='NOMINAL_COORDINATION_STRUCTURE_UNSUPPORTED' for d in s.diagnostics)
s,groups,_=run(['Иван','старший','и','Пётр'],['?']);assert groups is False
# A one-member group cannot be published as complete by answering zero.
s,groups,_=run(['Иван','старший','и','Пётр'],['1','1','1','0']);assert groups is False
print('F05 addressed groups: nonadjacent/three/OOV/repeated heads; exact source; other vs unknown; minimum cardinality; retired completion and mutated copies rejected: PASS')

# No lexical marker is needed, and no source occurrence is consumed as one.
s,groups,_=run(['Шмырлик','зелёный','Шмырлик','Пётр'],['1','1','1','2','2','0','2','0'])
assert groups[0]['member_refs']==['0','2','3'] and groups[0]['marker_refs']==[] and live(s,groups[0])
supersede(s,groups[0]['coordination_completion']['decision_ref'],'replacement')
assert not live(s,groups[0])

# Independent contextual offers for the same occurrence must all survive overlay.
from ah.formalizer.contextual_name_case import overlay
from ah.formalizer.component_policy import _morph
from ah.formalizer.state import MorphVariant
v1=_morph(MorphVariant('имя','NOUN',frozenset({'nom'}),origin='CONTEXTUAL',evidence_refs=('one',)))
v2=_morph(MorphVariant('имя','NOUN',frozenset({'acc'}),origin='CONTEXTUAL',evidence_refs=('two',)))
token=TokenEvidence('имя','t',0,3)
rows=[{'token_ref':'t','variants':[v1]},{'token_ref':'t','variants':[v2]}]
for ordered in (rows,list(reversed(rows))):
    out=overlay([token],[{'contextual_readings':ordered}])
    assert {tuple(v.cases) for v in out[0].variants}=={('nom',),('acc',)}
assert not token.variants
print('Contextual reading union: both peer-derived alternatives retained without source mutation: PASS')

# Separate groups remain separate; discovery ends only after its own negative proof.
s,groups,_=run(['А','Б','В','Г'],['1','1','2','0','2','1','3','2','0','2','0'])
assert [g['member_refs'] for g in groups]==[['0','1'],['2','3']]
assert all(live(s,g) for g in groups)
print('Marker-independent discovery: empty ScopeLexicon, asyndetic group, two distinct groups and explicit unsupported nested/alternative structure: PASS')
