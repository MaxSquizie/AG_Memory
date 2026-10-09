"""Each executed case compares actual AH/WAL outputs with untouched symbolic gold."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import pytest
from tools.formalizer_v7_runtime_adapter import run_case,Session
from tools.check_formalizer_v7_oracle import load_corpus,evaluate,compare,canonical

ROOT=Path(__file__).resolve().parents[1]/'data/formalizer_v7_oracle'
_,CASES=load_corpus(ROOT)

def stimulus(case):
    case=deepcopy(case)
    for step in case['steps']:step.pop('checks')
    return case

@pytest.mark.parametrize('case',CASES,ids=lambda c:c['case_id'])
def test_oracle(case):
    trace=run_case(stimulus(case),{})
    if trace['execution_status']=='BLOCKED':
        assert trace['blockers'] and not trace['checkpoints']
        pytest.skip('BLOCKED: '+str(trace['blockers']))
    assert trace['binding_manifest']['api_refs']
    previous={}
    for step,cp in zip(case['steps'],trace['checkpoints'],strict=True):
        assert cp['step_id']==step['id']
        for ck in step['checks']:assert evaluate(ck,cp['actual'],previous),(case['case_id'],ck,cp['actual'])
        previous[step['id']]=cp['actual']

def find(cid):return next(c for c in CASES if c['case_id']==cid)

def test_gold_not_available_to_exporter():
    original=find('TQ-00-00-0');mutated=deepcopy(original);mutated['steps'][0]['checks'][0]['value']='NO'
    assert run_case(stimulus(original),{})['checkpoints']==run_case(stimulus(mutated),{})['checkpoints']

@pytest.mark.parametrize('mutation',['wrong_answer','missing_answer'])
def test_comparator_rejects_actual_error(tmp_path,mutation):
    trace=run_case(stimulus(find('TQ-00-00-0')),{});cp=trace['checkpoints'][0]['actual']
    if mutation=='wrong_answer':cp['answer']['status']='NO'
    else:cp.pop('answer')
    dest=tmp_path/'actual.jsonl';dest.write_text(canonical(trace)+'\n')
    report=compare(ROOT,dest,['TQ-00-00-0']);assert report['failed_cases']==1

def test_unbound_is_never_pass(tmp_path):
    trace=run_case(stimulus(find('A01')),{});dest=tmp_path/'actual.jsonl';dest.write_text(canonical(trace)+'\n')
    report=compare(ROOT,dest,['A01'])
    assert report['status']=='BLOCKED' and report['blocked_cases']==1 and report['passed_cases']==0

def test_exporter_reads_actual_graph(tmp_path):
    ivan={'predicate':'ARRIVE','roles':{'AGENT':{'entity':'ivan'}}};petr={'entity':'petr'}
    s=Session([ivan,petr],tmp_path/'journal');uids,_,_=s.prepare('B',[ivan]);s.commit('B')
    ops=[];petr_uid=s.tree(petr,'fixture',ops)[0]
    from ah.formalizer.graph_ops import ensure_entity
    ensure_entity(s.store._core,ops[0].payload)
    original=s.store._store.get_hypernode(uids[0]);modified=replace(original,actants={next(iter(original.actants)):s.store._core.ref(petr_uid)})
    s.store._core.edit_element(s.store._store.domain_of(modified.uid),modified)
    assert s.decode(uids[0])['roles']['AGENT']==petr
