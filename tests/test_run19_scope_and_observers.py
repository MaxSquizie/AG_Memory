"""Recorded-run root causes, exercised through the actual native GUI contour.

Scripted choices check contracts; they do not claim better live model accuracy.
"""
import pytest
from pathlib import Path
from test_structural_relation_tasks import run, relation, bounds, unary, atom


def oracle_result(case_id,result):
    from tools.check_formalizer_v7_oracle import load_corpus,compare_case
    _,cases=load_corpus(Path(__file__).resolve().parents[1]/'data/formalizer_v7_oracle')
    case=next(c for c in cases if c['case_id']==case_id)
    return compare_case(case,{'schema_version':'v7-oracle-trace-1','case_id':case_id,
        'checkpoints':[{'step_id':'ingest','actual':result}]})


def test_modal_marker_returns_inner_negation_to_its_content(tmp_path,monkeypatch):
    steps=relation('POSSIBLE')+bounds('structural_introducer','может','не')+[
        ('relation_marker_role','RELATION_ONLY'),('relation_marker_role','«не»')]
    steps+=bounds('structural_introducer','может','может')+[
        ('structural_partition','PARTITION'),('structural_governor','Agreement/controller anchor «может»')]
    steps+=unary('NOT','не','не')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван может не прийти.',steps)
    expected={'operator':'POSSIBLE','operands':[{'operator':'NOT','operands':[atom('ARRIVE','ivan')]}]}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert result['diagnostics']['codes']==[]
    questions=[p for slot,p in script.calls if slot=='relation_marker_role']
    assert 'Question about ONE source word: «не»' in questions[-1]
    assert 'nested negation, modality or quantifier' in questions[-1]
    conflict=next(t for t in result['runtime']['ir']['syntax_trace'] if t.get('kind')=='STRUCTURAL_PARTITION_COVERAGE')
    assert conflict['status']=='REPAIRED'
    assert not any(slot=='structural_revision' for slot,_ in script.calls)


@pytest.mark.parametrize('reply',['?','ONE_SELECTED'])
def test_unknown_particle_scope_does_not_commit_the_simplified_formula(tmp_path,monkeypatch,reply):
    steps=relation('POSSIBLE')+bounds('structural_introducer','может','не')+[
        ('relation_marker_role','RELATION_ONLY'),('relation_marker_role',reply)]
    result,_=run(tmp_path,monkeypatch,'Иван может не прийти.',steps,default='?')
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    assert not any(t.get('required_content_refs') for t in result['runtime']['ir']['syntax_trace'])


def test_particle_can_belong_to_a_complete_lexical_modal_expression(tmp_path,monkeypatch):
    # Do not make the spelling «не» an unconditional inner NOT.
    result,script=run(tmp_path,monkeypatch,'Не исключено, что Иван пришёл.',
        unary('POSSIBLE','Не','что')+relation('LEXICAL'))
    assert result['assertions']['ah']==[{'operator':'POSSIBLE','operands':[atom('ARRIVE','ivan')]}]
    assert result['diagnostics']['codes']==[]
    questions=[p for slot,p in script.calls if slot=='relation_marker_role']
    assert any('Question about ONE source word: «Не»' in p for p in questions)
    assert any('Question about ONE source word: «исключено»' in p for p in questions)


def test_no_governor_choice_without_a_dependent_child_reading(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Возможно, Алексей передал книгу Марии.',
        unary('POSSIBLE','Возможно',',')+relation('LEXICAL'))
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah'][0]['operator']=='POSSIBLE'
    assert not any(slot=='structural_governor' for slot,_ in script.calls)
    frames=result['runtime']['ir']['frames']
    assert all(not f['semantic'].get('agreement_source_ref') for f in frames)


@pytest.mark.parametrize('kind,marker,body,last,predicate,theme',[
    ('POSSIBLE','можно','книгу','прочитать','READ','book'),
    ('NECESSARY','нужно','открыть','окно','OPEN','window'),
])
def test_query_observer_keeps_action_pattern_and_schema_without_an_actor(
        tmp_path,monkeypatch,kind,marker,body,last,predicate,theme):
    text='Верно ли, что '+(body+' '+marker+' '+last if predicate=='READ' else marker+' '+body+' '+last)+'?'
    steps=unary('QUERY','Верно','что')+unary(kind,marker,marker)
    if kind=='NECESSARY':steps+=[('structural_governor','INDEPENDENT')]
    steps+=relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,text,steps,kind='QUERY')
    expected={'operator':kind,'operands':[{'predicate':predicate,'roles':{'THEME':{'entity':theme}}}]}
    assert expected in result['generation']['observed_candidate_patterns']
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    assert result['coverage']['status']=='FULL_CANONICAL'
    ir=result['runtime']['ir']
    frame=next(f for f in ir['frames'] if f['semantic'].get('action_description'))
    assert frame['frame_id'] in result['runtime']['coverage_evidence']['closed_frame_ids']
    assert frame['semantic']['action_description']['unassigned_roles']==['SUBJECT']
    checked=oracle_result('NONFINITE-'+('06' if predicate=='READ' else '07')+'-question',result)
    assert checked['status']=='PASS',checked


@pytest.mark.parametrize('text,kind,marker,case_id',[
    ('Книгу можно прочитать.','POSSIBLE','можно','NONFINITE-06-base'),
    ('Нужно открыть окно.','NECESSARY','Нужно','NONFINITE-07-base'),
])
def test_agreed_modal_gold_retains_strict_operator_and_factivity_checks(tmp_path,monkeypatch,text,kind,marker,case_id):
    from copy import deepcopy
    steps=unary(kind,marker,marker)
    if kind=='NECESSARY':steps+=[('structural_governor','INDEPENDENT')]
    result,_=run(tmp_path,monkeypatch,text,steps+relation('LEXICAL'))
    checked=oracle_result(case_id,result)
    assert checked['status']=='PASS',checked
    wrong=deepcopy(result)
    wrong['assertions']['ah'][0]['operator']='NECESSARY' if kind=='POSSIBLE' else 'POSSIBLE'
    assert oracle_result(case_id,wrong)['status']=='FAIL'
    wrong=deepcopy(result)
    wrong['assertions']['ah'].append(wrong['assertions']['ah'][0]['operands'][0])
    assert oracle_result(case_id,wrong)['status']=='FAIL'


def test_query_markers_do_not_hide_an_unresolved_action(tmp_path,monkeypatch):
    from test_action_descriptions import ingest
    from tools.formalizer_v7_extended_binding import Session
    from tools.formalizer_v7_native_binding import native_coverage
    session=Session([],tmp_path/'coverage.log')
    state,_=ingest(session,monkeypatch,'Верно ли, что книгу можно прочитать?',
        unary('QUERY','Верно','что')+unary('POSSIBLE','можно','можно')+relation('LEXICAL'),'coverage','QUERY')
    for frame in state.frames:frame.semantic['structural_unresolved']=True
    coverage,_=native_coverage(state,session.release,session.store)
    assert coverage['level']=='NONE' and not coverage['covered_span_ids']


def test_gui_explains_preserved_inner_relation():
    from test_formalization_readable import sample
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    reader=ReadableInspection(Inspection(sample()))
    text=reader.task_choice({'marker_content_ref':'read'})
    assert 'вложенной связи' in text
