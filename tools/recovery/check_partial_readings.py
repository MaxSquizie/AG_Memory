"""Controlled partial-reading scenario; replies here are scripted, not model evidence."""
import json,re
from pathlib import Path
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session
from tempfile import TemporaryDirectory
workspace=TemporaryDirectory(prefix='recovery_partial_');out=Path(workspace.name)
calls=[]
def generate(self,prompt,**kw):
 slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
 labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M))
 answer='0' if 'Optional search:' in prompt else '1'
 if slot=='predicate_argument_role':
  target=re.search(r'What role does «([^»]+)»',prompt).group(1)
  prefix={'Иван':'core subject:','Анне':'recipient or addressee','сообщение':'core object:'}[target]
  answer=next(n for n,s in labels.items() if s.startswith(prefix))
 if slot=='predicate_argument_reading' and 'reading of «сообщение»' in prompt:answer=next(n for n,s in labels.items() if 'accusative' in s)
 if slot=='nominal_dependency' and 'attachment of «Анне»' in prompt:answer=','.join(n for n,s in labels.items() if s.startswith('Direct role RECIPIENT'))
 if slot=='predicate_argument_reading' and 'reading of «Анне»' in prompt:
  matches=[n for n,s in labels.items() if 'dative' in s]
  answer=','.join(matches) or '?'
 calls.append({'slot':slot,'prompt':str(prompt),'answer':answer})
 return answer
ChatBackend.generate=generate
text='Иван отправит Анне сообщение.'
p={'raw_input':{'text':text,'source_id':'partial-controlled','revision':1,'range':[0,len(text)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
s=Session([p],out/'journal.log');s.observer_contract='v7-observer-1'
r=execute_native(s,p,{'provider':'lmstudio','model':'controlled-contract','structure_mode':'region_probes'})
for name,obj in [('result',r),('state',s.native_states[-1]),('calls',calls)]: (out/(name+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
print(json.dumps({'assertions':r['assertions'],'diagnostics':r['diagnostics'],'partial':len(s.native_states[-1]['observation'].get('partial_compositions',[])),'calls':[(x['slot'],x['answer']) for x in calls]},ensure_ascii=False))

from copy import deepcopy
from types import SimpleNamespace as N
from ah.formalizer.partial_composition import validate
from ah.formalizer.composition_tree import validate as canonical_validate
raw=s.native_states[-1]
state=N(**{**raw,'decisions':{k:N(**{**v,'grounds':[N(**g) for g in v['grounds']]}) for k,v in raw['decisions'].items()},'frames':[N(**f) for f in raw['frames']]})
assert state.machine_state=='PARTIAL'
assert not r['assertions']['ah'] and not r['assertions']['journal']
assert len(state.observation['partial_compositions'])==1
record=state.observation['partial_compositions'][0]
assert validate(state,record,state.frames)
assert record['structure_complete'] and not record['write_eligible']
for mutation in ('role','reading_domain','choice'):
    changed=deepcopy(state);receipt=deepcopy(record)
    if mutation=='role':
        frame=next(f for f in changed.frames if f.frame_id in receipt['frame_refs'])
        frame.semantic['proposed_roles']['tok:14:18']='SUBJECT'
    elif mutation=='reading_domain':receipt['reading_domains'][0]['alternatives'][0]['reading']['lemma']='different'
    else:receipt['tree']['alternatives'].pop()
    try:validate(changed,receipt,changed.frames)
    except ValueError:pass
    else:raise AssertionError('partial receipt accepted '+mutation)
try:canonical_validate(state.frames,[record['tree']])
except ValueError as exc:assert str(exc)=='PARTIAL_COMPOSITION_NOT_WRITABLE'
else:raise AssertionError('choice became canonical')
print('PARTIAL: both readings retained; canonical write blocked; changed grounds rejected')
workspace.cleanup()
