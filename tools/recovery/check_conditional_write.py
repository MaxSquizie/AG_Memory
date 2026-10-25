"""Controlled original conditional through one durable clarification and T6.

Uses the existing TEST_ONLY lexical fixture and the native adapter. It checks
algorithm/consumer contracts, not model understanding or the production release.
Run with PYTHONPATH=.:src:tests:<pymorphy dependencies> python this_file.py.
Optional --out retains the exact provider inputs and committed diagnostic graph.
"""
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--out')
args=parser.parse_args()
from tempfile import TemporaryDirectory
from pathlib import Path
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,binary,Script,relation,bounds
import re,json
captured_calls=[]
original=Script.generate
def generate(self,prompt,**kwargs):
 slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
 captured_calls.append({'system':str(kwargs.get('system','')),'prompt':str(prompt),'slot':slot})
 labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M))
 answer=None
 if slot=='predicate_argument_role':
  target=re.search(r'What role does «([^»]+)»',prompt).group(1)
  prefix={'Иван':'core subject:','Мария':'core subject:','он':'core subject:','Петру':'recipient or addressee','Анне':'recipient or addressee','сообщение':'core object:'}[target]
  answer=next(n for n,s in labels.items() if s.startswith(prefix))
 if slot=='predicate_argument_reading':
  target=re.search(r'reading of «([^»]+)»',prompt).group(1)
  case={'Иван':'nominative','Мария':'nominative','он':'nominative','Петру':'dative','Анне':'dative','сообщение':'accusative'}[target]
  answer=','.join(n for n,s in labels.items() if case in s)
 if slot=='nominal_dependency' and 'attachment of «Анне»' in prompt:
  answer=','.join(n for n,s in labels.items() if s.startswith('Direct role RECIPIENT'))
 if slot=='implicit_argument':
  answer=next(n for n,s in labels.items() if s.startswith('Same participant as Иван'))
 if answer:
  self.calls.append((slot,prompt));return answer
 return original(self,prompt,**kwargs)
import test_structural_relation_tasks as fixture
from tools import formalizer_v7_native_binding as native
from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
captured={}
original_execute=fixture.execute_native
original_interpret=native.interpret_full
def execute(session,payload,config):
 captured['session']=session
 return original_execute(session,payload,config)
def interpret(*args,**kwargs):
 captured['selector']=args[2];captured['morph']=kwargs['morph']
 result=original_interpret(*args,**kwargs);captured['state'],captured['report']=result
 return result
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
 patch.setattr(fixture,'execute_native',execute)
 patch.setattr(native,'interpret_full',interpret)
 patch.setattr(Script,'generate',generate)
 steps=relation('IF_ELSE')+bounds('structural_operand_1','Иван','пришла')+bounds('structural_operand_2','он','Петру')+bounds('structural_operand_3','отправит','сообщение')+[('structural_partition','PARTITION')]
 steps+=relation('CONTENT')+bounds('structural_content','Мария','пришла')+bounds('structural_parent','Иван','узнает')+[('structural_owner','Content belongs to predicate «узнает»'),('structural_partition','PARTITION'),('structural_content_role','OBJECT:EMBEDDED')]+relation('LEXICAL')
 steps+=relation('NOT')+bounds('structural_introducer','не','не')+[('structural_partition','PARTITION')]+relation('LEXICAL')*3
 r,s=run(Path(tmp),patch,'Если Иван узнает, что Мария не пришла, он позвонит Петру, а иначе отправит Анне сообщение.',steps)
 assert not r['assertions']['ah'] and not r['assertions']['journal']
 assert captured['state'].machine_state=='PARTIAL'

 session=captured['session'];binding=InterpretationRunBinding(session.store._journal)
 adapter=FormalizerAdapter(captured['selector'],morph=captured['morph'],store=session.store,binding=binding,release=session.release,ignition=session.native_ignition)
 receipt=adapter._receipt(captured['state'],captured['report'])
 assert receipt.terminal=='RESOLUTION_ONLY' and not receipt.committed_fragments
 assert len(receipt.perception.native_clarifications)==1
 offer=receipt.perception.native_clarifications[0]
 option=next(o for o in offer.options if 'анна;' in o.label)
 # The projection has to preserve source ownership and supported payloads.
 from ah.formalizer.reading_clarifications import project
 from copy import deepcopy
 requests=[r['payload'] for r in session.store._journal.scan_unprocessed()
           if r['payload'].get('kind')=='CLARIFICATION_REQUEST']
 request=next(r for r in requests if r['decision_ref'].startswith('reading-clarification:'))
 choice=next(o for o in request['options'] if 'анна;' in o['label'])
 assert len(project(request,choice))==2
 for mutation in ('scope','reading','payload','retired'):
  changed=deepcopy(request)
  equivalence=next(r for r in changed['generation_snapshot']['syntax_trace']
                   if r.get('kind')=='PARTIAL_READING_EQUIVALENCE' and r['decision_ref']==request['decision_ref'])
  if mutation=='scope':equivalence['domains'][0]['token_ref']='other-occurrence'
  elif mutation=='reading':
   chosen=next(o for o in equivalence['options'] if o['candidate_id']==choice['candidate_id'])
   chosen['reading']['lemma']='different'
  elif mutation=='retired':
   changed['generation_snapshot']['syntax_trace'].append({'kind':'COMPOSITION_PROBE_SUPERSEDED','previous_decision_ref':equivalence['domains'][0]['decision_ref'],'decision_ref':'replacement'})
  else:
   domain=equivalence['domains'][0]
   row=next(r for r in changed['generation_snapshot']['syntax_trace']
            if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==domain['domain_ref'])
   row['supported_payloads'].clear()
  try:project(changed,choice)
  except ValueError:pass
  else:raise AssertionError('accepted changed '+mutation)
 receipt=adapter.clarify(option.key,source_text=r['runtime']['ir']['text'])
 assert receipt.terminal=='APPLIED' and len(receipt.committed_fragments)==1 and not receipt.diagnostics
 assert not receipt.perception.native_clarifications and not s.errors
 snapshot=adapter.diagnostic_snapshot();graph=snapshot['committed_graph'];nodes=graph['nodes']
 assert not graph['truncated'] and not graph['remaining_refs']
 def event(template=None,lemma=None):
  found=[n for n in nodes.values() if (template is not None and n.get('template_ref')=='fixture:T:'+template)
         or (lemma is not None and n.get('lexical_lemma')==lemma)]
  assert len(found)==1,(template,lemma,found)
  return found[0]
 learn=event(lemma='узнать');arrive=event('ARRIVE');call=event('CALL');send=event('SEND')
 ivan='fixture:language:M:ivan'
 assert learn['actants']['SUBJECT']==call['actants']['SUBJECT']==send['actants']['SUBJECT']==ivan
 assert call['actants']['RECIPIENT']=='fixture:language:M:petr'
 assert arrive['actants']['SUBJECT']=='fixture:language:M:maria'
 anna=graph['entities'][send['actants']['RECIPIENT']]
 message=graph['entities'][send['actants']['OBJECT']]
 assert anna['mention_ref']=='tok:75:79' and message['mention_ref']=='tok:80:89'
 negative_content=nodes[learn['actants']['OBJECT']]
 assert negative_content['function_id']=='NOT' and negative_content['operands']==[arrive['uid']]
 implications=[n for n in nodes.values() if n.get('function_id')=='IMPLIES']
 assert len(implications)==2
 positive=next(n for n in implications if n['operands'][1]==call['uid'])
 negative=next(n for n in implications if n['operands'][1]==send['uid'])
 assert positive['operands'][0]==learn['uid']
 otherwise=nodes[negative['operands'][0]]
 assert otherwise['function_id']=='NOT' and otherwise['operands']==[learn['uid']]
 conjunction=next(n for n in nodes.values() if n.get('function_id')=='AND')
 assert set(conjunction['operands'])=={n['uid'] for n in implications}
 assert set(graph['receipt_refs'])=={conjunction['uid'],*(n['uid'] for n in implications)}
 # Retrying the same durable choice must not reinterpret or append a second write.
 before=[row for row in session.store._journal.scan_unprocessed()]
 again=adapter.clarify(option.key,source_text=snapshot['source_text'])
 assert again.terminal=='APPLIED' and again.committed_fragments==receipt.committed_fragments
 assert list(session.store._journal.scan_unprocessed())==before
 if args.out:
  out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
  (out/'conditional_snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str))
  (out/'conditional_inputs.json').write_text(json.dumps(captured_calls,ensure_ascii=False,indent=2))
 print('PASS: PARTIAL -> one clarification -> APPLIED; sender, roles, nested scope, fact roots and retry verified')
