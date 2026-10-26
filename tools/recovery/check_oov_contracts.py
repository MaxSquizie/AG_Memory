"""Focused controlled contract checks; the supplied answers are not model evidence."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
import re

from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session
from ah.formalizer import composition_morphology
from ah.formalizer.morphology_domain import function_support,function_use

text='Я попросил Диму зафлюмить квендрик но он сказал что квендрик не работает.'
answers=iter(['7','1','1,12'])
calls=[];captured={}
original=composition_morphology.prepare

def prepare(runtime,*args,**kwargs):
    value=original(runtime,*args,**kwargs)
    captured.update(state=runtime.state,tokens=value)
    return value

def generate(self,prompt,**kwargs):
    slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
    calls.append((slot,str(prompt)))
    return next(answers) if slot=='structural_oov_function' else '?'

with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    patch.setattr(ChatBackend,'generate',generate)
    patch.setattr(composition_morphology,'prepare',prepare)
    payload={'raw_input':{'text':text,'source_id':'oov-contract','revision':1,'range':[0,len(text)],
                         'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
    result=execute_native(Session([payload],Path(tmp)/'j'),payload,
        {'provider':'lmstudio','model':'controlled-contract','structure_mode':'region_probes'})

state=captured['state'];tokens=[t for t in captured['tokens'] if t.span=='квендрик']
rows=[r for r in state.syntax_trace if r.get('kind')=='MORPHOLOGY_FUNCTION_RESTRICTION'
      and r['token_ref'] in {t.token_id for t in tokens}]
assert len(rows)==2 and rows[0]['decision_ref']!=rows[1]['decision_ref']
assert [{v.pos for v in t.variants} for t in tokens]==[{'NOUN'},{'NOUN','ADVB'}]
assert len([p for s,p in calls if s=='structural_oov_function'])==3
assert function_support(state,tokens[0],rows[0])=={'NOUN'}
assert not function_support(state,tokens[1],rows[0])
assert not result['assertions']['ah']
changed=deepcopy(rows[0]);changed['address']['token_ref']=tokens[1].token_id
assert not function_support(state,tokens[1],changed)
changed=deepcopy(rows[0]);changed['interpretation_version']+=1
assert not function_support(state,tokens[0],changed)
reading=next(r['reading'] for r in state.syntax_trace if r.get('kind')=='MORPHOLOGY_USE'
             and r['token_ref']==tokens[0].token_id)
assert function_use(state,tokens[0].token_id,reading,rows[0]['decision_ref'],'NOUN')
changed=deepcopy(reading);changed['cases']=['nom']
assert not function_use(state,tokens[0].token_id,changed,rows[0]['decision_ref'],'NOUN')
assert not function_use(state,tokens[1].token_id,reading,rows[0]['decision_ref'],'NOUN')

# A legacy raw-page offer is rejected at persistence and when its old key is used.
from ah.formalizer.clarification_liveness import prune,obsolete_reason
page=next(iter(state.component_probe_records))
state.clarification_candidates.append({'decision_ref':page,'kind':'COMPONENT','options':[{},{}]})
prune(state)
assert not any(r['decision_ref']==page for r in state.clarification_candidates)
assert obsolete_reason({'decision_ref':page,'generation_snapshot':{
    'component_probe_records':state.component_probe_records}})=='CLARIFICATION_PAGE_NOT_ADMISSIBLE'
print('PASS: distinct OOV addresses; supported POS domain retained; cross-occurrence/feature promotion rejected; legacy page offer rejected')
