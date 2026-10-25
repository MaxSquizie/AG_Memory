"""Controlled source-reference contrasts; not model evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import Script,relation,bounds,unary,content_steps
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session
import re,json
original=Script.generate
text='Иван сказал, что Пётр не пришёл, и Мария это повторила.'
steps=relation('AND')+bounds('structural_operand_1','Иван','пришёл')+bounds('structural_operand_2','Мария','повторила')+[('structural_partition','PARTITION')]
steps+=content_steps('сказал','Пётр','пришёл')+unary('NOT','не','не')+relation('LEXICAL')
steps+=relation('CONTENT_REFERENCE')+bounds('content_pointer','это','это')+[('structural_owner','Content belongs to predicate «повторила»'),('structural_content_role','OBJECT:QUOTED')]+relation('LEXICAL')
for mode in ('same','unavailable','unsupported_control'):
 other=mode=='unavailable'
 calls=[]
 def generate(self,prompt,**kwargs):
  slot=re.search(r'Decision slot: (\S+)',prompt).group(1);labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M));answer=None
  if slot=='content_reference_presence':answer='2'
  if slot=='content_reference_source':
   answer=next((n for n,s in labels.items() if s.startswith('The intended content is not') if other),None) if other else next(n for n,s in labels.items() if s.startswith('Content «Пётр не пришёл»'))
  if slot=='content_reference_kind':answer='2' if mode=='unsupported_control' else '1'
  if slot=='lexical_recovery':answer='0'
  if answer:self.calls.append((slot,prompt))
  else:answer=original(self,prompt,**kwargs)
  calls.append({'slot':slot,'prompt':str(prompt),'answer':answer})
  return answer
 with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
  s=Script(steps);patch.setattr(Script,'generate',generate);patch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:s.generate(prompt,**kw))
  p={'raw_input':{'text':text,'source_id':'reference-contrast','revision':1,'range':[0,len(text)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
  session=Session([p],Path(tmp)/'journal.log');session.observer_contract='v7-observer-1'
  r=execute_native(session,p,{'provider':'lmstudio','model':'controlled-contract','structure_mode':'region_probes'})
  assert not s.errors,s.errors
  facts=r['assertions']['ah']
  if mode=='same':
   assert not s.steps and not r['diagnostics']['codes'] and len(facts)==3
   def atoms(value):
    if value.get('operator')=='AND':
     for child in value['operands']:yield from atoms(child)
    else:yield value
   asserted=[f for fact in facts for f in atoms(fact)]
   assert {f['predicate'] for f in asserted}=={'SAY','OPEN:повторить'}
   contents=[f['roles']['CONTENT'] for f in asserted]
   expected={'operator':'NOT','operands':[{'predicate':'ARRIVE','roles':{'AGENT':{'entity':'petr'}}}]}
   assert all(c==expected for c in contents)
   sources=[f for f in r['runtime']['ir']['frames'] if f['semantic'].get('content_source_frame')]
   assert len(sources)==1
  else:
   assert not facts and not r['assertions']['journal']
   expected='CONTENT_SOURCE_UNAVAILABLE' if other else 'CONTENT_REBIND_UNSUPPORTED'
   assert expected in r['diagnostics']['codes'],r['diagnostics']
  print('PASS:',mode)
