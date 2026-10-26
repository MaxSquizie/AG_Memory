"""Native OOV parent evidence survives descent and local child revision."""
from tempfile import TemporaryDirectory
from pathlib import Path
from pytest import MonkeyPatch
import re
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session
from ah.formalizer import composition_morphology
from ah.formalizer.morphology_domain import function_restrictions,function_support,attested
from ah.formalizer.component_policy import _morph

text='Я попросил Диму зафлюмить квендрик но он сказал что квендрик не работает и попросил меня подождать.'
calls=[];relations=0;oov=iter(['7','1,12','1']);children=[];captured={}
def generate(self,prompt,**kwargs):
    global relations
    slot=re.search(r'Decision slot: (\S+)',prompt).group(1);calls.append(slot)
    labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M))
    if slot=='structural_oov_function':return next(oov)
    if slot=='structural_relation':relations+=1;return '6' if relations==1 else '?'
    targets={'structural_operand_1_start':'Start at «Я»','structural_operand_1_end':'End after «квендрик»',
             'structural_operand_2_start':'Start at «он»','structural_operand_2_end':'End after «подождать»'}
    if slot in targets:return next(n for n,label in labels.items() if label.startswith(targets[slot]))
    if slot.endswith('_continue') or slot=='structural_function_owner':return '0'
    if slot in {'structural_partition','relation_marker_role'}:return '1'
    return '?'

original=composition_morphology.prepare
def prepare(runtime,region,tokens,request,cfg):
    value=original(runtime,region,tokens,request,cfg);captured.update(state=runtime.state,runtime=runtime)
    if region.source_range!=(0,len(text)):
        before=len(calls)
        # Exercise re-entry into this child producer with revised local inputs.
        value=original(runtime,region,tokens,request,{**cfg,'_task_constraints':'controlled local revision'})
        assert len(calls)==before
        for token in value:
            if token.is_oov():
                records=function_restrictions(runtime.state,token.token_id)
                assert records
                expected=function_support(runtime.state,token,records[-1])
                assert {v.pos for v in token.variants}==expected
                # Richer independent proposals may remain in the candidate
                # domain, but the inherited POS answer cannot attest them.
                for v in token.variants:
                    if v.cases or v.number is not None or v.features:
                        assert not attested(runtime.state,token,_morph(v))
                children.append((token.token_id,expected))
    return value

with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    patch.setattr(ChatBackend,'generate',generate);patch.setattr(composition_morphology,'prepare',prepare)
    payload={'raw_input':{'text':text,'source_id':'oov-inheritance','revision':1,'range':[0,len(text)],
                         'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
    r=execute_native(Session([payload],Path(tmp)/'j'),payload,
        {'provider':'lmstudio','model':'controlled-contract','structure_mode':'region_probes'})
assert calls.count('structural_oov_function')==3
assert children and any(s=={'INFN'} for _,s in children)
assert any(s=={'NOUN','ADVB'} for _,s in children)
assert not r['assertions']['ah']
trace=captured['state'].syntax_trace
imports=[x for x in trace if x.get('kind')=='MORPHOLOGY_FUNCTION_IMPORT']
assert imports
for row in imports:
    assert any(x.get('kind')=='DISPATCH_SOURCE_READ' and x.get('task_ref')==row['parent_task']
               and x.get('revision')==row['parent_revision'] for x in trace)
dispatcher=captured['runtime'].dispatcher
row=imports[-1];child=row['task_scope'].rsplit(':',1)[0]
assert dispatcher.valid(child)
dispatcher.invalidate(row['parent_task'],'CONTROLLED_PARENT_EVIDENCE_CHANGED')
assert not dispatcher.valid(child)
print('PASS: occurrence domains imported into children; local revision retains parent proof; parent invalidation reaches child; no repeated OOV probe or invented features')
