"""Controlled conversational source-reference scenario over TEST_ONLY resources.

This diagnostic checks native interpretation and the committed graph; its
scripted replies are not live-model evidence. --out retains the actual inputs.
"""
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--out');args=parser.parse_args()
import json,re
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import Script,relation,bounds,unary,content_steps
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session
from tools import formalizer_v7_native_binding as native
from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
captured={}
from ah.formalizer import content_sources
original_read=content_sources.read
def read_source(runtime,option):
 captured['source_runtime']=runtime;captured['source_option']=option
 return original_read(runtime,option)
original_interpret=native.interpret_full
def interpret(*args,**kwargs):
 captured['selector']=args[2];captured['morph']=kwargs['morph']
 result=original_interpret(*args,**kwargs);captured['state'],captured['report']=result
 return result
original=Script.generate
calls=[]
def generate(self,prompt,**kwargs):
 slot=re.search(r'Decision slot: (\S+)',prompt).group(1);labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M));answer=None
 if slot=='predicate_argument_role':
  target=re.search(r'What role does «([^»]+)»',prompt).group(1)
  prefix={'Я':'core subject:','я':'core subject:','он':'core subject:','Сашу':'recipient or addressee','Катю':'recipient or addressee','посылку':'core object:'}.get(target)
  if prefix:answer=next(n for n,s in labels.items() if s.startswith(prefix))
 if slot=='predicate_argument_reading':
  target=re.search(r'reading of «([^»]+)»',prompt).group(1)
  case={'Я':'nominative','я':'nominative','он':'nominative','Сашу':'accusative','Катю':'accusative','посылку':'accusative'}.get(target)
  if case:
   options=[n for n,s in labels.items() if case in s and (target not in {'Я','я','он'} or 'pos: pronoun' in s) and (target!='Сашу' or 'masculine' in s)]
   if options:answer=','.join(options)
 if slot=='temporal_function' and 'вчера' in prompt:
  answer=next((n for n,s in labels.items() if 'вчера' in s),None)
 if slot=='temporal_source_end':answer=next((n for n,s in labels.items() if 'вчера' in s),None)
 if slot=='implicit_argument':answer=next((n for n,s in labels.items() if s.startswith('Same participant as Сашу')),None)
 if slot=='omitted_content_presence':answer='2' if 'Target predicate «успеет»' in prompt else '1'
 if slot=='content_reference_presence':answer='2' if 'TARGET: я попросил' in prompt else '1'
 if slot=='content_reference_source':answer=next((n for n,s in labels.items() if s.startswith('Content «забрать посылку»')),None)
 if slot=='content_reference_kind':answer='2'
 if slot=='content_reference_control':answer=next((n for n,s in labels.items() if '= omitted SUBJECT' in s or '= RECIPIENT «Катю»' in s),None)
 if answer:self.calls.append((slot,prompt))
 else:answer=original(self,prompt,**kwargs)
 calls.append({'slot':slot,'prompt':str(prompt),'system':str(kwargs.get('system','')),'answer':answer})
 return answer
text='Я вчера попросил Сашу забрать посылку, но он сказал, что не успеет, и предложил, чтобы я попросил об этом Катю.'
steps=relation('AND')+bounds('structural_operand_1','Я','посылку')+bounds('structural_operand_2','он','Катю')+[('structural_partition','PARTITION')]
steps+=relation('CONTENT')+bounds('structural_content','забрать','посылку')+bounds('structural_parent','Я','Сашу')+[('structural_owner','Content belongs to predicate «попросил»'),('structural_partition','PARTITION'),('structural_content_role','OBJECT:HYPOTHETICAL')]+relation('LEXICAL')+[('structural_control','Same RECIPIENT')]+relation('LEXICAL')
steps+=relation('AND')+bounds('structural_operand_1','он','успеет')+bounds('structural_operand_2','предложил','Катю')+[('structural_partition','PARTITION')]
steps+=content_steps('сказал','не','успеет',parent_first='он')+unary('NOT','не','не')+relation('LEXICAL')+[('structural_content_role','OBJECT:HYPOTHETICAL')]
steps+=relation('CONTENT')+bounds('structural_content','я','Катю')+bounds('structural_parent','предложил','предложил')+[('structural_owner','Content belongs to predicate «предложил»'),('structural_partition','PARTITION'),('structural_content_role','OBJECT:HYPOTHETICAL')]+relation('LEXICAL')+relation('CONTENT_REFERENCE')+bounds('content_pointer','об','этом')+[('structural_owner','Content belongs to predicate «попросил»'),('structural_content_role','OBJECT:HYPOTHETICAL')]+relation('LEXICAL')
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
 patch.setattr(native,'interpret_full',interpret)
 patch.setattr(content_sources,'read',read_source)
 s=Script(steps);patch.setattr(Script,'generate',generate);patch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:s.generate(prompt,**kw))
 p={'raw_input':{'text':text,'source_id':'conversation-recovery-controlled','revision':1,'range':[0,len(text)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE','source_timestamp':'2026-10-26T12:00:00+03:00','timezone':'Europe/Moscow'}}
 session=Session([p],Path(tmp)/'journal.log');session.observer_contract='v7-observer-1'
 r=execute_native(session,p,{'provider':'lmstudio','model':'controlled-contract','structure_mode':'region_probes'})
 adapter=FormalizerAdapter(captured['selector'],morph=captured['morph'],store=session.store,binding=InterpretationRunBinding(session.store._journal),release=session.release,ignition=session.native_ignition)
 receipt=adapter._receipt(captured['state'],captured['report'])
 adapter._capture_diagnostics(captured['state'],captured['report'],receipt)
 assert receipt.terminal=='APPLIED' and len(receipt.committed_fragments)==1
 assert not receipt.diagnostics and not receipt.perception.native_clarifications,(receipt.diagnostics,receipt.perception.native_clarifications)
 assert not s.errors and not s.steps
 snapshot=adapter.diagnostic_snapshot();graph=snapshot['committed_graph'];nodes=graph['nodes']
 assert not graph['truncated'] and not graph['remaining_refs']
 entities={v['name']:uid for uid,v in graph['entities'].items()}
 sasha,katya,parcel=(entities[name] for name in ('Сашу','Катю','посылку'))
 speaker='fixture:language:M:speaker'
 def node(lemma=None,template=None,**roles):
  found=[n for n in nodes.values() if (n.get('lexical_lemma')==lemma if lemma is not None else n.get('template_ref')=='fixture:T:'+template)
         and all(n.get('actants',{}).get(k)==v for k,v in roles.items())]
  # AND elimination can publish an occurrence-qualified copy of a timed node.
  assert found,(lemma,template,roles)
  assert all(n['actants']==found[0]['actants'] for n in found)
  return found[0]
 request=node('попросить',SUBJECT=speaker,RECIPIENT=sasha)
 say=node(template='SAY',SUBJECT=sasha)
 propose=node('предложить',SUBJECT=sasha)
 proposed_request=nodes[propose['actants']['OBJECT']]
 assert proposed_request['actants']['SUBJECT']==speaker and proposed_request['actants']['RECIPIENT']==katya
 negation=nodes[say['actants']['OBJECT']]
 assert negation['function_id']=='NOT' and len(negation['operands'])==1
 manage=nodes[negation['operands'][0]]
 assert manage['lexical_lemma']=='успеть' and manage['actants']['SUBJECT']==sasha
 pickup=nodes[request['actants']['OBJECT']]
 omitted_pickup=nodes[manage['actants']['OBJECT']]
 katya_pickup=nodes[proposed_request['actants']['OBJECT']]
 assert pickup['actants']==omitted_pickup['actants']=={'SUBJECT':sasha,'OBJECT':parcel}
 assert katya_pickup['actants']=={'SUBJECT':katya,'OBJECT':parcel}
 assert pickup['template_ref']==omitted_pickup['template_ref']==katya_pickup['template_ref']
 def asserted(ref):
  n=nodes[ref]
  if n.get('function_id')=='AND':
   for operand in n['operands']:yield from asserted(operand)
  else:yield n
 facts=[n for ref in graph['receipt_refs'] for n in asserted(ref)]
 allowed={request['content_key'],say['content_key'],propose['content_key']}
 assert {n['content_key'] for n in facts}==allowed
 assert r['time_assertions']['count']==1
 time=r['time_assertions']['records'][0]
 assert nodes[time['target_ref']]['actants']==request['actants']
 from datetime import datetime
 from zoneinfo import ZoneInfo
 day=datetime.fromtimestamp(time['region']['lo'],ZoneInfo('Europe/Moscow'))
 assert str(day.date())=='2026-10-25' and day.hour==0
 assert not r['time']['invented_past_intervals'] and not r['time']['clock_default_used']
 state=captured['state']
 from ah.formalizer.content_reference_functions import validate_reference
 uses=[(f,role,slot) for f in state.frames for role,slot in f.semantic.get('proposition_args',{}).items() if slot.get('content_reference')]
 assert len(uses)==2 and all(validate_reference(state,*use) for use in uses)
 # Mutating a dependent identity or lexical origin cannot keep an old receipt.
 from copy import deepcopy
 owner,role,slot=uses[0]
 row=next(r for r in state.syntax_trace if r.get('receipt_ref')==slot['content_reference'])
 fid=next(iter(row['frame_bases']));copied=next(f for f in state.frames if f.frame_id==fid)
 for key,value in [('shared_implicit_arguments',{'SUBJECT':{'frame_ref':'other','role':'SUBJECT'}}),('content_source_frame','other')]:
  old=deepcopy(copied.semantic.get(key));copied.semantic[key]=value
  assert not validate_reference(state,owner,role,slot)
  copied.semantic[key]=old
 assert validate_reference(state,owner,role,slot)
 source_id=next(iter(row['source_frame_bases']))
 original_frame=next(f for f in state.frames if f.frame_id==source_id)
 old_roles=deepcopy(original_frame.semantic['proposed_roles'])
 original_frame.semantic['proposed_roles']={}
 assert not validate_reference(state,owner,role,slot)
 original_frame.semantic['proposed_roles']=old_roles
 assert validate_reference(state,owner,role,slot)
 # Every copy consumes the lexical decision of its original source.
 for f in state.frames:
  if f.semantic.get('content_source_frame'):
   d=state.decisions[f.frame_id+'|predicate_value']
   assert d.outcome=='RESOLVED' and any(h.get('validator')=='content_lexical_source' for h in d.history)
 runtime=captured['source_runtime'];option=captured['source_option'];dispatcher=runtime.dispatcher
 dependents=[key for key,node in dispatcher.nodes.items() if option['source_task'] in node['reads']]
 assert dependents and all(dispatcher.valid(key) for key in dependents)
 dispatcher.invalidate(option['source_task'],'DIAGNOSTIC_SOURCE_CHANGE')
 assert all(not dispatcher.valid(key) for key in dependents)
 try:dispatcher.read(option['source_task'],option['source_revision'])
 except ValueError:pass
 else:raise AssertionError('stale source reused')
 if args.out:
  out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
  (out/'conversation_snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str))
  (out/'conversation_inputs.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2))
 print('PASS: APPLIED; content source, subject substitution, lexical reuse, time, scopes and assertion roots verified')
