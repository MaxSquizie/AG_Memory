"""F05 source-domain contrasts; real selection codec, no live model."""
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.relation_quantifiers import binder_candidates
from ah.formalizer.structural_tasks import choose,licensed
from ah.formalizer.quantifier_composition import bind
from ah.formalizer.spatial_references import source_candidates

s=t0('шмырлик шмырлик')
s.evidence=[TokenEvidence('шмырлик','a',0,7),TokenEvidence('шмырлик','b',8,15)]
r=TextRegion('r','SENTENCE',(0,15),('a','b'),None)
release=NS(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
cfg={'max_candidates':8,'context_chars':2000}
options=list(binder_candidates(s.evidence))
assert [x['head_ref'] for x in options]==['a','b']
sel=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:'2')
value,proof=choose(s,release,sel,r,cfg,'structural_binder_head',options,'Select the bound participant mention.')
assert value['head_ref']=='b' and licensed(s,proof,head_ref='b')
assert all(not t.variants for t in s.evidence)
# Address selection alone cannot manufacture a nominal restriction.
rule={'head_ref':'b','structural_license':proof,'head_license':proof,
      'restriction_pattern':{'head_pos':['NOUN','NPRO']}}
assert bind(s,release,sel,r,[],{(0,7,'FORALL'):([s.evidence[0]],rule)},cfg) is None
assert any(d.code=='QUANTIFIER_HEAD_UNRESOLVED' for d in s.diagnostics)

def anchor(ref,start):
    return {'anchor_ref':ref,'entity_ref':'place:'+ref,'source_range':[start,start+5]}
anchors=[anchor('far',0),anchor('near',90),anchor('later',150),anchor('self',100)]
options,bounds=source_candidates(anchors,[100,120],'self',40)
assert [a['anchor_ref'] for a in options]==['far','near','later']
assert bounds==[0,155] and bounds[1]-bounds[0]>40
# Budget overflow is visible to prepare; no older/future candidate is dropped.
assert anchors[0]['source_range']==[0,5]
options[0]['source_range'][0]=999
assert anchors[0]['source_range']==[0,5]
assert source_candidates([], [100,120],'self',40)==([],[80,120])
print('F05: OOV/repeated binder addresses retained; no invented nominal reading; distant/following anchors retained; full context exceeds budget explicitly: PASS')
