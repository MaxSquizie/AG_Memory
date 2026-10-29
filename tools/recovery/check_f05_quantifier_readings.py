"""Binder contracts on constructed readings; real probe codec, no live model."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import MorphVariant,FrameCandidate
from ah.formalizer.regions import TextRegion
from ah.formalizer.quantifier_composition import compatible,bind,licensed
from ah.formalizer.morphology_domain import clean

marker=MorphVariant('каждый','ADJF',cases=frozenset({'nom'}))
reading=MorphVariant('студент','NOUN',cases=frozenset({'nom'}))
unknown=replace(reading,cases=frozenset())
other=replace(reading,cases=frozenset({'acc'}))
assert compatible(marker,clean(unknown),['cases'])
assert compatible(replace(marker,cases=frozenset()),clean(reading),['cases'])
assert not compatible(marker,clean(other),['cases'])
rule={'operator':'FORALL','pattern':'каждый','variable_sort':'ENTITY','attachment_kinds':['QUANTIFIED_NOMINAL'],
      'restriction_pattern':{'head_pos':['NOUN','NPRO'],'agreement':['cases','number','gender'],
                             'role':'SUBJECT','body_operator':'IMPLIES'}}
release=NS(sha256='release',entries=lambda kind: [rule] if kind=='ScopeLexicon' else [{'max_rule_steps':100}])
cfg={'max_candidates':8,'context_chars':2000}
def run(readings,answer='1'):
    s=t0('каждый студент');s.budget.llm_limit=20
    a,t=s.evidence;a.variants=(marker,);t.variants=tuple(readings)
    r=TextRegion('r','SENTENCE',(0,len(s.text)),tuple(x.token_id for x in s.evidence),None)
    frames=[FrameCandidate('f'+str(i),'FLAT','body',(),argument_token_refs=(t.token_id,),
        semantic={'morph_bindings':{t.token_id:clean(v)}}) for i,v in enumerate(readings)]
    calls=[]
    def reply(prompt):calls.append(prompt);return answer
    result=bind(s,release,NS(selection_reply_format='SELECT_LABELS_V1',select=reply),r,frames,
                {(a.start,a.end,'FORALL'):([a],rule)},cfg)
    return s,t,frames,result,calls
s,t,frames,result,calls=run([unknown,unknown])
assert result and len(calls)==1
restriction=next(iter(result.values()))['restriction']
assert licensed(s,release,restriction)
assert all(t.token_id in f.semantic['bound_arguments'] for f in frames)
# Attestation of a different source reading is not authority to change the selected one.
s.evidence[1].variants=(*s.evidence[1].variants,reading)
restriction.semantic['morph_bindings'][t.token_id]=clean(reading)
assert not licensed(s,release,restriction)
for values in [[reading,unknown],[reading,other]]:
    s,t,frames,result,calls=run(values)
    assert result is None and not calls
    assert any(d.code=='QUANTIFIER_READING_UNRESOLVED' for d in s.diagnostics)
    assert all('bound_arguments' not in f.semantic for f in frames)
for answer in ['?','0']:
    s,t,frames,result,calls=run([unknown],answer)
    assert result is None and len(calls)==1
    assert 'bound_arguments' not in frames[0].semantic
print('PASS: unknown agreement reaches probe; conflicting selected uses cannot be bound; no partial mutation; exact reading retained; none/unknown do not license restriction')
