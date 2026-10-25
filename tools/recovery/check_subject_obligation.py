"""Controlled semantic contrasts for open-predicate subject obligations; no live model."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,Script
import re
original=Script.generate
for text,answer in [('Подмигнул.','1'),('Смеркается.','2'),('Морозит.','?')]:
 calls=[]
 def generate(self,prompt,**kwargs):
  slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
  calls.append({'system':str(kwargs.get('system','')),'prompt':str(prompt),'slot':slot})
  if slot=='predicate_subject_presence':
   self.calls.append((slot,prompt));return answer
  return original(self,prompt,**kwargs)
 with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
  patch.setattr(Script,'generate',generate)
  r,s=run(Path(tmp),patch,text,relation('LEXICAL'))
  facts=r['assertions']['ah']
  if answer=='?':
   assert not facts and not r['assertions']['journal']
   assert 'PREDICATE_SUBJECT_PRESENCE_UNRESOLVED' in r['diagnostics']['codes']
  else:
   assert len(facts)==1 and not r['diagnostics']['codes']
   frame=next(f for f in r['runtime']['ir']['frames'] if not f['semantic'].get('structural_unresolved'))
   assert frame['semantic']['subject_presence']['omitted']==(answer=='1')
   assert bool(frame['semantic'].get('implicit_arguments'))==(answer=='1')
   assert ('AGENT' in facts[0]['roles'])==(answer=='1')
  print('PASS:',text,'subject presence:',answer)
