"""Common dispatcher obligations; constructed proofs, no model claims."""
from dataclasses import replace
from pytest import MonkeyPatch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.composition_dispatcher import Dispatcher
from ah.formalizer.task_contracts import CONTRACTS,TaskResult,TaskOutcome,produced
from test_composition_dispatcher import setup_morphology
from ah.formalizer.composition_session import session
from ah.formalizer.component_constraints import compatible_bundle

s=t0('source');d=Dispatcher(s);calls=[]
contract=CONTRACTS['MORPHOLOGY']
def child():
    return d.run('child',None,lambda:calls.append('child') or contract.output_sort,kind='MORPHOLOGY',contract=contract)
def parent():return d.run('parent',None,child,kind='COMPOSITION')
assert parent()=='READING_DOMAIN'
contract=replace(contract,output_sort='REVISED_READING_DOMAIN')
assert child()=='REVISED_READING_DOMAIN' and not d.valid('parent')
assert parent()=='REVISED_READING_DOMAIN' and len(calls)==2
try:d.run('child',None,lambda:1,kind='GRAMMAR',contract=contract)
except ValueError as e:assert str(e)=='DISPATCH_CONTRACT_KIND_MISMATCH'
else:raise AssertionError('misdeclared producer accepted')
for value in [[],[1],True,42]:assert not produced('GRAMMAR',value).search_complete
assert produced('GRAMMAR',TaskResult([],TaskOutcome.GENERATOR_NONE_FIT,True,True)).search_complete

state,release,region,cfg=setup_morphology('Иван пришёл.')
token,predicate=state.evidence[:2]
frame=FrameCandidate('frame','FLAT',state.text,(),predicate_token_ref=predicate.token_id,
    semantic={'proposed_roles':{token.token_id:'SUBJECT'}})
with MonkeyPatch.context() as patch,session(state,release) as runtime:
    from ah.formalizer import structural_tasks
    patch.setattr(structural_tasks,'licensed',lambda state,proof,**kw:proof['live'])
    def check():return compatible_bundle(state,region,[frame])
    def task():return runtime.dispatcher.run('generator',None,check,kind='COMPOSITION')
    assert task()
    runtime.dispatcher.run('independent',None,lambda:123,kind='MORPHOLOGY')
    row={'kind':'ESTABLISHED_PREDICATE_ROLE','region_ref':region.region_id,'task_scope':None,
         'predicate_ref':predicate.token_id,'token_ref':token.token_id,'role':'OBJECT','proof':{'live':True}}
    # Empty constraint-set read is a real dependency on future insertions.
    state.syntax_trace.append(row)
    assert not runtime.dispatcher.valid('generator') and runtime.dispatcher.valid('independent')
    assert task() is False
    row['role']='SUBJECT'
    assert task() is True
    row['proof']['live']=False
    assert task() is False
    state.syntax_trace.remove(row)
    assert task() is True
    # Neither a sibling area nor another hypothesis changes this generator.
    state.syntax_trace.append({**row,'region_ref':'other','proof':{'live':True}})
    state.syntax_trace.append({**row,'task_scope':'other','proof':{'live':True}})
    assert runtime.dispatcher.valid('generator')
    attempts=[]
    def changing():
        old=check();attempts.append(old)
        if len(attempts)==1:state.syntax_trace.append({**row,'role':'OBJECT','proof':{'live':True}})
        return old
    assert runtime.dispatcher.run('changing',None,changing,kind='COMPOSITION') is False
    assert attempts==[True,False]
print('PASS: changed contract invalidates consumers; kind mismatch rejected; no implicit search closure; empty/changed/retired scoped constraints; unrelated branches; mid-compute insertion')
