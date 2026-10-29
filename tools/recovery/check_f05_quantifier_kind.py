"""Actual semantic-choice codec; morphology cannot decide numeric meaning."""
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import MorphVariant
from ah.formalizer.regions import TextRegion
from ah.formalizer.relation_quantifiers import quantifier_kind
from ah.formalizer.structural_tasks import licensed
from ah.formalizer.component_probe_replay import supersede
from ah.formalizer.quantifier_composition import bind
release=NS(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
cfg={'max_candidates':8,'context_chars':2000}
def run(text,answer,variant=None):
    s=t0(text)
    if variant:s.evidence[0].variants=(variant,)
    r=TextRegion('r','SENTENCE',(0,len(text)),tuple(t.token_id for t in s.evidence),None)
    prompts=[]
    def reply(prompt):prompts.append(prompt);return answer
    result=quantifier_kind(s,release,NS(selection_reply_format='SELECT_LABELS_V1',select=reply),r,s.evidence,cfg)
    assert len(prompts)==1
    return s,r,result
s,r,result=run('один', '1',MorphVariant('один','NUMR',features=frozenset({'Anum'})))
assert result[0]['candidate_id']=='NONNUMERIC' and licensed(s,result[1])
s2,r2,result2=run('не меньше половины','2')
assert result2[0]['candidate_id']=='ARITHMETIC'
for answer in ('?','0','1,2'):
    assert run('какое-то выражение',answer)[2] is None
supersede(s,result[1]['decision_ref'],'replacement')
rule={'quantifier_kind_license':result[1]}
assert bind(s,release,None,r,[],{(0,len(s.text),'EXISTS'):(s.evidence,rule)},cfg) is None
assert s.diagnostics[-1].code=='QUANTIFIER_KIND_UNRESOLVED'
print('Quantifier kind: numeral hypothesis does not veto nonnumeric use; arithmetic without NUMR; unknown/none/multiple preserved; revoked classification rejected: PASS')
