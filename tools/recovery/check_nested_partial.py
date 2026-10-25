"""Controlled recursive partial composition, not a live-model evaluation."""
from tempfile import TemporaryDirectory
from pathlib import Path
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,binary,Script
import re,json
original=Script.generate
def generate(self,prompt,**kwargs):
 slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
 labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M))
 answer=None
 if slot=='predicate_argument_role':
  target=re.search(r'What role does «([^»]+)»',prompt).group(1)
  prefix={'Иван':'core subject:','Мария':'core subject:','Анне':'recipient or addressee','сообщение':'core object:'}[target]
  answer=next(n for n,s in labels.items() if s.startswith(prefix))
 if slot=='predicate_argument_reading':
  target=re.search(r'reading of «([^»]+)»',prompt).group(1)
  case={'Иван':'nominative','Мария':'nominative','Анне':'dative','сообщение':'accusative'}[target]
  answer=','.join(n for n,s in labels.items() if case in s)
 if slot=='nominal_dependency' and 'attachment of «Анне»' in prompt:
  answer=','.join(n for n,s in labels.items() if s.startswith('Direct role RECIPIENT'))
 if answer:
  self.calls.append((slot,prompt));return answer
 return original(self,prompt,**kwargs)
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
 patch.setattr(Script,'generate',generate)
 r,s=run(Path(tmp),patch,'Если Иван пришёл, то Мария отправит Анне сообщение.',binary('IMPLIES',('Иван','пришёл'),('Мария','сообщение')))
 ir=r['runtime']['ir']
 assert ir['machine_state']=='PARTIAL' and not r['assertions']['ah'] and not r['assertions']['journal']
 records=ir['observation']['partial_compositions']
 assert len(records)==1 and records[0]['tree']['operator']=='IMPLIES'
 assert 'choice_ref' in records[0]['tree']['operands'][1]
 print(r['diagnostics'],r['assertions'])
 print([(x.get('kind'),x.get('task_outcome')) for x in r['runtime']['ir']['syntax_trace'] if x.get('kind') in {'COMPOSITION_PARTIAL','COMPOSITION_REJECTED'}])
