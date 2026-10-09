"""Meaningful runtime boundary checks for completed component oracle bindings."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_component_binding import component_action,released_fixture
from tools.formalizer_v7_fixture_binding import fixture_action
from tools.formalizer_v7_state_binding import state_action,dsl_probe
from ah.formalizer.v7_pipeline import _observation,interpret_full
from ah.formalizer.run_binding import InterpretationRunBinding


@pytest.mark.parametrize('override',[{'source_id':''},{'revision':True},{'revision':0},
    {'language':'xx'},{'batch_kind':'INVALID'},{'request_kind':'INVALID'},
    {'range':[-1,3]},{'range':[3,1]},{'text':'\ud800'},
    {'source_timestamp':'2026-10-09T12:00:00'}])
def test_raw_input_rejected_before_durable_binding(tmp_path,override):
    s=Session([],tmp_path/'raw.log')
    raw={'source_id':'source','revision':1,'text':'Мария спит.','range':[0,12],**override}
    before=s.store.read_global_head()
    with pytest.raises(ValueError):_observation(raw['text'],version=1,raw_input=raw)
    assert s.store.read_global_head()==before


def test_revision_aliases_share_observation_and_canonical_input():
    base={'source_id':'source','range':[0,12],'text':'Мария спит.'}
    one=_observation(base['text'],version=1,raw_input={**base,'revision':1})
    alias=_observation(base['text'],version=1,raw_input={**base,'source_revision':1})
    newer=_observation(base['text'],version=2,raw_input={**base,'revision':2})
    assert one==alias
    assert one['observation_id']==newer['observation_id']


@pytest.mark.parametrize('mutation,code',[('same_revision_different_text','INPUT_CONFLICT'),
    ('same_pair_different_context_hash','INTEGRITY_ERROR'),
    ('same_pair_different_resource_hash','INTEGRITY_ERROR')])
def test_replay_identity_mutates_exactly_one_declared_input_dimension(tmp_path,mutation,code):
    s=Session([],tmp_path/'identity.log')
    result=state_action(s,'replay_identity',{'mutation':mutation})
    assert result['diagnostics']['codes']==[code]
    assert result['store']['new_record_count']==0


def test_live_source_conflict_and_historical_replay(tmp_path):
    s=Session([],tmp_path/'conflict.log');b=InterpretationRunBinding(s.store._journal)
    raw={'source_id':'source','range':[0,12],'revision':1}
    _,first=interpret_full('Иван пришёл.',None,None,s.store,b,run_id='GR1',raw_input=raw)
    assert first.t5_eligibility=='RESOURCE_MISSING'
    _,conflict=interpret_full('Пётр пришёл.',None,None,s.store,b,run_id='GR1',raw_input=raw)
    assert conflict.t5_eligibility=='INPUT_CONFLICT'
    assert not s.store.ledger.data['nodes']
    assert any(r['payload'].get('code')=='INPUT_CONFLICT' for r in s.store._journal.scan_unprocessed())
    # A fresh larger revision does not erase the immutable historic input.
    interpret_full('Пётр пришёл.',None,None,s.store,b,version=2,run_id='GR2',raw_input={**raw,'revision':2})
    _,old=interpret_full('Иван пришёл.',None,None,s.store,b,run_id='GR1',raw_input=raw)
    assert old.t5_eligibility=='RESOURCE_MISSING'


def test_concurrent_versions_cannot_claim_one_revision_with_different_text(tmp_path):
    s=Session([],tmp_path/'race.log');b=InterpretationRunBinding(s.store._journal)
    raw={'source_id':'source','range':[0,12],'revision':1}
    interpret_full('Иван пришёл.',None,None,s.store,b,run_id='BASE',raw_input=raw)
    barrier=Barrier(2);original=b.acquire
    def acquire(owner,*args,**kwargs):
        if owner in {'V2','V3'}:barrier.wait(timeout=5)
        return original(owner,*args,**kwargs)
    b.acquire=acquire
    def run(version,text):return interpret_full(text,None,None,s.store,b,version=version,
        run_id='V'+str(version),raw_input={**raw,'revision':2})[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run,2,'Пётр пришёл.'),pool.submit(run,3,'Мария ушла.')]
        reports=[f.result(timeout=10) for f in futures]
    assert sorted(r.t5_eligibility for r in reports)==['INPUT_CONFLICT','RESOURCE_MISSING']
    inputs=[r['payload']['snapshot_data'] for r in s.store._journal.scan_unprocessed()
            if r['payload'].get('kind')=='run_bind' and r['payload']['snapshot_data'].get('revision')==2]
    assert len(inputs)==1


@pytest.mark.parametrize('kind',['R1','R-WK','EvidencePriorityPolicy'])
@pytest.mark.parametrize('mutation',['missing_required_field','unknown_field','wrong_field_type','duplicate_id'])
def test_optional_norm_resource_schemas_use_valid_signed_baseline(tmp_path,kind,mutation):
    s=Session([],tmp_path/'release.log');baseline,_=released_fixture(s)
    assert baseline.entries(kind)
    result=component_action(s,'load_release',{'mutate_kind':kind,'mutation':mutation})
    assert result['release']['available'] is False
    assert result['diagnostics']['codes']==['RESOURCE_MISSING']


def test_independent_lexical_and_structural_proposal_budgets():
    from ah.formalizer.provider_adapter import ProviderAdapter,BudgetSnapshot,BudgetExceeded
    provider=ProviderAdapter('fixture',frozenset({'propose_local'}),lambda _: '{}',
        budget=BudgetSnapshot(tp_calls=2,lexical_calls=4,token_limit=10000))
    for i in range(4):provider.propose_lexical(str(i),'G')
    with pytest.raises(BudgetExceeded):provider.propose_lexical('overflow','G')
    for i in range(2):provider.propose_local(str(i),'G')
    with pytest.raises(BudgetExceeded):provider.propose_local('overflow','G')
    assert provider._ordinals['G']==6


def test_fixed_fixture_permutations_and_real_recorded_byte_replay(tmp_path):
    s=Session([],tmp_path/'fixed.log')
    base=fixture_action(s,'run_fixed_fixture',{'fixture':'SIMPLE_LOCATIVE','mutation':None})
    assert base['decision']['outcome']=='RESOLVED'
    assert len(base['ir']['decision_ids'])>=2
    for mutation in ['R_entries_order','source_iteration_order','constraint_iteration_order','replay_provider_bytes']:
        result=fixture_action(s,'run_fixed_fixture',{'fixture':'SIMPLE_LOCATIVE','mutation':mutation,'isolated_store':True})
        for key in ['ir','state','diagnostics']:assert result[key]==base[key]
        if mutation=='replay_provider_bytes':assert result['provider']['transport_call_count']==0


@pytest.mark.parametrize('state',['COMMITTED_LIVE','SUPERSEDED','JOURNALED','AMBIGUOUS','PROVISIONAL','REJECTED'])
@pytest.mark.parametrize('stage',['SRL','T2','T3'])
def test_rx_read_uses_canonical_commit_boundary(tmp_path,state,stage):
    s=Session([],tmp_path/'rx.log')
    result=state_action(s,'rx_read',{'record_state':state,'record_stage':stage,'read_stage':stage,'open_lexical':True})
    assert result['rx']['readable']==(state=='COMMITTED_LIVE')
    assert result['rx']['writes_uncommitted'] is False
    assert result['supports']['root_from_rx']==0
    assert result['rx']['record_stage_runtime']==('T1' if stage=='SRL' else stage)


@pytest.mark.parametrize('mutation,materialized',[('attachment',True),('sense_conflict',False)])
def test_invalid_open_key_mutations_preserve_actual_norm_observation(tmp_path,mutation,materialized):
    s=Session([],tmp_path/'key.log')
    result=state_action(s,'open_template_keys',{'base':{'observation':'O1','revision':1,
        'surface':'глоркнул','role':'AGENT','attachment':'nsubj'},'changed_dimension':mutation})
    assert result['open']['key_equal'] is True
    assert result['open']['materialized'] is materialized
    assert result['stimulus']['baseline_valid'] is True
    assert result['stimulus']['mutation_contract_valid'] is False


def test_invalid_dsl_baseline_cannot_be_negative_boundary_proof():
    result=dsl_probe('rule x:1 {stage=SRL}','unknown_field')
    assert result['stimulus']['baseline_valid'] is False
    assert result['stimulus']['baseline_error']


def test_search_interruption_has_actual_frozen_decision_state(tmp_path):
    from tools.formalizer_v7_decision_binding import decision_action
    s=Session([],tmp_path/'decision.log')
    result=decision_action(s,'resolve_tuples',{'surviving_tuple_count':1,
        'each_value_has_positive_ground':True,'search_complete':False,'source_complete':True,
        'source_statuses':['FOUND','CHECKED_EMPTY','CHECKED_EMPTY','CHECKED_EMPTY','CHECKED_EMPTY']})
    assert result['decision']['outcome']=='COMPUTATION_LIMIT'
    assert result['decision']['materializable'] is False
