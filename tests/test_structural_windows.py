"""Addressed window permissions: native execution plus isolated scheduler guards."""
from types import SimpleNamespace as NS
from copy import deepcopy
import re
from test_structural_open_forest import native
from ah.formalizer.composition_session import _current
from ah.formalizer import structural_windows as windows
from ah.formalizer.structural_frontier import StructuralFrontier


TEXT='Неверно что неверно что неверно что неверно что Иван пришёл'


def answer(slot,prompt):
    labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
    if 'Optional search:' in prompt:return '0'
    tokens=_current.get().area_inputs[1]
    if slot=='structural_relation':
        phrase='Negation of a proposition' if len(tokens)>2 else 'One lexical predication'
        return next((n for n,label in labels if phrase in label),'0')
    if slot in {'relation_marker_role','structural_partition'}:return '1'
    if slot in {'structural_introducer_start','structural_introducer_end'}:
        start=slot.endswith('start');token=tokens[0 if start else 1]
        prefix=('Start at' if start else 'End after')+' «'+token.span+'» @'+str(token.start if start else token.end)
        return next((n for n,label in labels if label.startswith(prefix)),'0')
    return '?'


def test_native_window_continues_not_chain_with_unknown_sibling(tmp_path,monkeypatch):
    state,result,_=native(tmp_path,monkeypatch,('NOT','LEXICAL'),answer,text=TEXT)
    snapshot=next(iter(state.observation['structural_frontiers'].values()))
    assert max(j['depth'] for j in snapshot['jobs'])==5
    assert snapshot['windows'] and snapshot['windows'][0]['first_depth']==4
    assert snapshot['windows'][0]['last_depth']==6
    assert snapshot['cost']['constraint_checks'] and snapshot['cost']['production_seconds']>0
    assert any(r.get('reason')=='RELATION_PRODUCER_NOT_CONNECTED' for r in state.syntax_trace)
    assert not result['assertions']['ah'] and not snapshot['structure_complete']


def test_retirement_between_authorization_and_start_blocks_branch(tmp_path,monkeypatch):
    original=windows.authorize;revoked=[]
    def authorize(driver,job,check):
        permit=original(driver,job,check)
        if permit:
            driver.state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED',
                'decision_ref':job['parent_shell']['partition_proof']['decision_ref']})
            revoked.append(job['job_ref'])
        return permit
    monkeypatch.setattr(windows,'authorize',authorize)
    state,result,_=native(tmp_path,monkeypatch,('NOT','LEXICAL'),answer,text=TEXT)
    started={r['job_ref'] for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_FRONTIER_EVENT' and r['event']=='started'}
    assert revoked and not started.intersection(revoked)
    assert any(r.get('event')=='window_revoked' for r in state.syntax_trace)
    assert not result['assertions']['ah']


def test_generation_change_during_production_stops_following_jobs(tmp_path,monkeypatch):
    original=StructuralFrontier.event;changed=[]
    def event(self,job,kind,**extra):
        original(self,job,kind,**extra)
        if kind=='completed' and not changed:
            self.runtime.tasks.feedback={'change':'during-production'};changed.append(True)
    monkeypatch.setattr(StructuralFrontier,'event',event)
    state,result,_=native(tmp_path,monkeypatch,('NOT','LEXICAL'),answer,text=TEXT)
    events=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_FRONTIER_EVENT']
    assert changed and sum(r['event']=='started' for r in events)==1
    assert any(r.get('reason')=='GENERATION_CHANGED' for r in events)
    assert not result['assertions']['ah']


def fixture():
    jobs={}
    for depth in range(1,8):
        ref=str(depth)
        jobs[ref]={'job_ref':ref,'depth':depth,'parent_job_ref':str(depth-1) if depth>1 else None,
                   'parent_shell':None,'forest':None,'state':NS(syntax_trace=[]),'status':'QUEUED'}
    return NS(jobs=jobs,generation_ref='generation',windows=[],sync=lambda j:None,event=lambda *a,**k:None)


def test_permit_is_local_three_levels_and_identity_bound():
    driver=fixture();job=driver.jobs['4'];check=windows.inspect(driver,job)
    permit=windows.authorize(driver,job,check);assert permit
    assert [windows.admitted(driver,driver.jobs[str(d)]) for d in (4,5,6,7)]==[True,True,True,False]
    saved=deepcopy(permit);permit['generation_ref']='other'
    assert not windows.admitted(driver,job)
    driver.windows=[saved];driver.jobs.pop('2')
    assert not windows.admitted(driver,job)
    assert not windows.inspect(driver,job)['check_complete']


def test_exact_exclusion_blocks_but_unrelated_or_retired_does_not(monkeypatch):
    # Scheduler-level contract: native receipt correctness is covered separately
    # in test_partition_exclusions, not simulated by this verifier stub.
    driver=fixture();job=driver.jobs['4']
    shell={'receipt_digest':'shell','combination_ref':'selected'}
    job['parent_shell']=shell
    row={'kind':'STRUCTURAL_PARTITION_EXCLUSION','exclusion_ref':'negative',
         'candidate':{'combination_ref':'selected'}}
    job['state'].syntax_trace=[row]
    monkeypatch.setattr(windows,'live',lambda *a:True)
    monkeypatch.setattr(windows,'evidence_state',lambda state,*a,**k:state)
    monkeypatch.setattr(windows,'exclusion_live',lambda *a:True)
    check=windows.inspect(driver,job)
    assert check['reason']=='COMBINATION_EXCLUDED' and windows.authorize(driver,job,check) is None
    row['candidate']['combination_ref']='different'
    assert windows.inspect(driver,job)['check_complete']
    row['candidate']['combination_ref']='selected'
    monkeypatch.setattr(windows,'exclusion_live',lambda *a:False)
    assert windows.inspect(driver,job)['check_complete']


def test_ready_shallow_sibling_precedes_admitted_deeper_job_even_in_reversed_queue(monkeypatch):
    from ah.formalizer import structural_frontier as frontier
    monkeypatch.setattr(frontier,'one_level',lambda *a:None)
    sequences=[]
    for reverse in (False,True):
        state=NS(syntax_trace=[],diagnostics=[],observation={},budget=NS(llm_exhausted=False))
        runtime=NS(state=state,dispatcher=NS(spent=0,limit=100))
        driver=object.__new__(StructuralFrontier)
        driver.state=state;driver.runtime=runtime;driver.generation_ref='generation';driver.windows=[]
        driver.cost={'constraint_checks':0,'validation_seconds':0.,'production_seconds':0.}
        driver.generation_current=lambda:True
        def job(ref,depth,parent,status):
            return {'job_ref':ref,'depth':depth,'parent_job_ref':parent,'parent_shell':None,
                    'forest':None,'state':state,'runtime':runtime,'status':status,'results':[],
                    'cfg':{},'region':None,'tokens':[],'request':None,'child':None}
        jobs=[job('root',1,None,'PRODUCED'),job('A',4,'root','PRODUCED'),
              job('B',4,'root','QUEUED'),job('A-child',5,'A','QUEUED')]
        driver.jobs={j['job_ref']:j for j in (reversed(jobs) if reverse else jobs)}
        windows.authorize(driver,driver.jobs['A'],windows.inspect(driver,driver.jobs['A']))
        driver.run()
        sequences.append([r['job_ref'] for r in state.syntax_trace if r.get('event')=='started'])
    assert sequences==[['B','A-child'],['B','A-child']]


def test_local_resource_stop_does_not_block_other_native_siblings(tmp_path,monkeypatch):
    from ah.formalizer import structural_frontier as frontier
    from test_structural_conditional_shells import boundaries
    original=frontier.one_level;blocked=[]
    def one_level(state,*args):
        if not blocked:
            blocked.append(True);state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE','injected-local-limit')
            return None
        return original(state,*args)
    monkeypatch.setattr(frontier,'one_level',one_level)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    snapshot=next(iter(state.observation['structural_frontiers'].values()))
    children=[j for j in snapshot['jobs'] if j['depth']==2]
    assert blocked and len(children)==4
    assert sum(j['status']=='PENDING_RESOURCE' for j in children)==1
    assert all(j['status']!='QUEUED' for j in children)
    assert not result['assertions']['ah']
