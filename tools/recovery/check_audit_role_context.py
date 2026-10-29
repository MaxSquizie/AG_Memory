"""Actual role question producers; scripted answers and a stub child parser."""
from types import SimpleNamespace
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence,FrameCandidate,MorphVariant
from ah.formalizer.regions import TextRegion
from ah.formalizer.spatial_references import prepare
from ah.formalizer.relative_pronoun import compose

class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,*answers):self.answers=iter(answers);self.prompts=[]
    def select(self,prompt):self.prompts.append(str(prompt));return next(self.answers)
proposal={'max_rule_steps':100,'spatial_references':{'rules':[],'context_chars':1000,'max_candidates':8}}
release=SimpleNamespace(sha256='r',entries=lambda kind:([{'role_id':'SUBJECT'},{'role_id':'LOCATION'}]
    if kind=='RoleRegistry' else [proposal]))
s=t0('Иван идёт');s.evidence=[TokenEvidence('Иван','a',0,4),TokenEvidence('идёт','p',5,9,variants=(MorphVariant('идти','VERB'),))]
r=TextRegion('r','SENTENCE',(0,9),('a','p'),None);s.region_forest=SimpleNamespace(regions=[r])
f=FrameCandidate('f','FLAT','идёт',(),predicate_token_ref='p',argument_token_refs=('a',),source_range=(0,9),semantic={'proposed_roles':{'a':'SUBJECT'}})
s.frames=[f];sel=Selector('5','1');prepare(s,release,sel)
assert 'Preserve these established assignments' in sel.prompts[1] and '«Иван» at 0' in sel.prompts[1]
assert s.decisions['f|spatial-function|role'].candidates==('LOCATION',)
assert next(iter(f.semantic['spatial_slots'].values()))['rule']['role_id']=='LOCATION'
s=t0('человек который пришёл')
h=TokenEvidence('человек','h',0,7,variants=(MorphVariant('человек','NOUN',frozenset({'nom'})),))
m=TokenEvidence('который','m',8,15,variants=(MorphVariant('который','NPRO',frozenset({'nom'})),))
p=TokenEvidence('пришёл','p',16,22)
s.evidence=[h,m,p];r=TextRegion('r','SENTENCE',(0,22),('h','m','p'),None);s.region_forest=SimpleNamespace(regions=[r])
sel=Selector('1','1')
with patch('ah.formalizer.component_refinement.compose_area',return_value=[]):
    compose(s,release,sel,r,[m,p],None,h,h.variants[0],{'general':True},
            {'max_candidates':8,'context_chars':2000,'open_case_roles':{'nom':'SUBJECT'}},0)
assert 'Established antecedent: «человек» at 0' in sel.prompts[1]
assert 'Established role inside the description: core subject' in sel.prompts[1]
assert 'Preserve this role' in sel.prompts[1]
print('F04 actual spatial/relative role producers preserve established assignments: PASS')
