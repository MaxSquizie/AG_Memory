"""Actual typed goal channel, WAL decisions, retraction and decision-first replay."""
from dataclasses import replace
import pytest
from ah.formalizer.goal_executor import GoalExecutor,GoalStore,GoalRequest,PathRecord,_path_key
from ah.formalizer.goal_channel import execute,decision_for
from ah.formalizer.temporal_license import point,cont
from tools.formalizer_v7_runtime_adapter import Session,witness

P={'predicate':'ARRIVE','roles':{'AGENT':{'entity':'ivan'}}}
Q={'predicate':'ARRIVE','roles':{'AGENT':{'entity':'petr'}}}
OR={'operator':'OR','operands':[P,Q]};NOT={'operator':'NOT','operands':[Q]}
ALL={'operator':'FORALL','operands':[{'bound_var':'x'},{'operator':'IMPLIES','operands':[{'predicate':'STUDENT','roles':{'THEME':{'bound_var':'x'}}},{'predicate':'PASS_EXAM','roles':{'AGENT':{'bound_var':'x'}}}]}]}
RESTR={'predicate':'STUDENT','roles':{'THEME':{'entity':'ivan'}}}

@pytest.fixture
def session(tmp_path):return Session([OR,NOT],tmp_path/'journal')

def request(session,root_point=5):
    return session.goal_request('OR_ELIMINATION',OR,[NOT],[witness({'kind':'POINT','t':root_point}),witness({'kind':'INTERVAL','bounds':[3,7],'semantics':'CONTINUOUS'})])[0]

def test_fresh_and_same_run_idempotent(session):
    req=request(session);a=execute(session.store,req);b=execute(session.store,req)
    assert a==b and a['outcome']=='APPLIED' and a['created']
    assert len(session.store.ledger.data['goal_paths'])==1
    assert len([r for r in session.store._journal.scan_unprocessed(0) if r['payload'].get('kind')=='GOAL_TERMINAL'])==1

def test_new_run_same_path_noop(session):
    req=request(session);execute(session.store,req);r=execute(session.store,replace(req,goal_run_id='GR2'))
    assert r['outcome']=='APPLIED_NOOP' and not r['created']
    assert len(session.store.ledger.data['goal_paths'])==1

def test_disjoint_not_region_aborts(session):
    r=execute(session.store,request(session,9))
    assert r['reason']=='GOAL_LICENSE_FAILED' and not session.store.ledger.data['goal_paths']

def test_withdrawal_between_pending_and_decision(session):
    req=request(session)
    r=execute(session.store,req,interleave=lambda:session.store.retract_observation('oracle:premises',1,trigger_ref='race'))
    assert r['reason']=='GOAL_PREMISES_STALE' and not session.store.ledger.data['goal_paths']

def test_existing_path_dead_is_aborted(session):
    req=request(session);execute(session.store,req)
    session.store.retract_observation('oracle:premises',1,trigger_ref='after')
    r=execute(session.store,replace(req,goal_run_id='GR2'))
    assert r['reason']=='GOAL_PREMISES_STALE' and len(session.store.ledger.data['goal_paths'])==1

def test_assertion_only_withdrawal_live_support_license_failure(session):
    req=request(session);execute(session.store,req)
    session.store.retract(req.temporal_premise_assertion_refs[-1],reason='assertion-only')
    assert all(s in session.store.ledger.paths() for s in req.premise_support_ids)
    r=execute(session.store,replace(req,goal_run_id='GR2'))
    assert r['reason']=='GOAL_LICENSE_FAILED'

def test_historical_applied_immutable_under_withdrawal(session):
    req=request(session);first=execute(session.store,req)
    session.store.retract_observation('oracle:premises',1,trigger_ref='after')
    assert execute(session.store,req)==first
    assert session.store.ledger.query_proposition(first['conclusion_ref'])['answer']=='UNKNOWN'

def test_crash_after_decision_before_terminal(session,monkeypatch):
    from ah.formalizer import goal_channel
    req=request(session)
    def crash(*args):raise RuntimeError('after decision')
    with monkeypatch.context() as m:
        m.setattr(goal_channel,'finish',crash)
        with pytest.raises(RuntimeError,match='after decision'):execute(session.store,req)
    session.store.retract_observation('oracle:premises',1,trigger_ref='in crash window')
    session.action('recover',{})
    assert decision_for(session.store,'GR1')['outcome']=='APPLIED'
    r=execute(session.store,req)
    assert r['outcome']=='APPLIED' and session.store.ledger.query_proposition(r['conclusion_ref'])['answer']=='UNKNOWN'

def test_forall_actual_instantiation(tmp_path):
    s=Session([ALL,RESTR],tmp_path/'journal')
    req,_=s.goal_request('FORALL_INST',ALL,[RESTR],[witness({'kind':'INTERVAL','bounds':[0,10],'semantics':'CONTINUOUS'}),witness({'kind':'POINT','t':5})])
    r=execute(s.store,req)
    assert r['outcome']=='APPLIED' and s.store.ledger.query_proposition(r['conclusion_ref'],point=5)['answer']=='YES'

def test_memory_unverified_form_cannot_assert():
    s=GoalStore();s.live_premises.update({'s1','s2'})
    r=GoalExecutor(s).execute(GoalRequest('G','OR_ELIMINATION',('s1','s2'),'P'))
    assert r['reason']=='GOAL_FORM_NOT_VERIFIED' and not s.paths and not s.nodes

@pytest.mark.parametrize('live,expected',[(True,'APPLIED_NOOP')],ids=['noop'])
def test_memory_existing_path_full_four_component_key(live,expected):
    s=GoalStore();s.live_premises.add('s');req=GoalRequest('G','OR_ELIMINATION',('s',),'P')
    n=s.ensure_node('P');s.paths[_path_key(req)]=PathRecord('D','OR_ELIMINATION',('s',),n)
    assert GoalExecutor(s).execute(req)['outcome']==expected

@pytest.mark.parametrize('rule,premises,operator,reason',[('FOREIGN',('s',),None,'GOAL_RULE_UNKNOWN'),('OR_ELIMINATION',(),None,'GOAL_NO_PREMISES'),('OR_ELIMINATION',('s',),'AND','GOAL_FORM_MISMATCH')])
def test_invalid_rule_form_or_no_premises(rule,premises,operator,reason):
    s=GoalStore();s.live_premises.add('s')
    r=GoalExecutor(s).execute(GoalRequest('G',rule,premises,'P',conclusion_operator=operator))
    assert r['reason']==reason and not s.paths
