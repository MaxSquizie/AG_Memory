"""Contract regressions with controlled probes, not a model-quality benchmark."""
from pathlib import Path
import pytest

from test_structural_relation_tasks import run, relation, unary


@pytest.mark.parametrize('operator,source,marker',[
    ('NOT','Неверно, что Пётр вошёл.','Неверно'),
    ('POSSIBLE','Возможно, что Пётр вошёл.','Возможно'),
])
def test_act_belongs_to_whole_operator_not_its_operand(tmp_path,monkeypatch,operator,source,marker):
    result,script=run(tmp_path,monkeypatch,source,unary(operator,marker,'что')+relation('LEXICAL'),
                      observer_contract='v7-observer-2')
    assert result['assertions']['ah']==[{'operator':operator,'operands':[
        {'predicate':'ENTER','roles':{'AGENT':{'entity':'petr'}}}]}]
    prompts=[p for slot,p in script.calls if slot=='speech_act']
    assert len(prompts)==1 and 'Context span: '+source.rstrip('.') in prompts[0]
    assert result['modus']=='DECLARATIVE'
    assert result['observer']['contract']=='v7-observer-2'


def test_host_query_never_becomes_asserted_negation(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Неверно, что Пётр вошёл?',
        unary('NOT','Неверно','что')+relation('LEXICAL'),kind='QUERY',observer_contract='v7-observer-2')
    assert not result['assertions']['ah'] and result['modus']=='QUERY'
    assert not any(slot=='speech_act' for slot,p in script.calls)


def test_selected_time_has_one_owner_and_observer_accepts_its_license(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Вчера Пётр вошёл.',relation('LEXICAL')+[
        ('temporal_function','A time expression starts at «Вчера»'),
        ('temporal_source_end','End after «Вчера»')],observer_contract='v7-observer-2',
        raw_extra={'source_timestamp':'2026-10-09T12:00:00+00:00'})
    assert result['assertions']['ah']==[{'predicate':'ENTER','roles':{'AGENT':{'entity':'petr'}}}]
    assert result['time_assertions']['semantics']==['EXISTENTIAL']
    assert result['time']['invented_past_intervals']==[]
    assert result['time']['licenses'][0]['token_refs']==['tok:0:5']
    assert not any(slot=='temporal_source_start' for slot,p in script.calls)


def test_open_observer_preserves_occurrence_and_real_roles(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Алексей флукнул книгу.',[
        ('structural_oov_function','VERB')]+relation('LEXICAL')+[
        ('predicate_function','Predicate occurrence «флукнул»'),
        ('predicate_argument_role','core subject:'),
        ('predicate_argument_role','core object:')],observer_contract='v7-observer-2')
    assert result['assertions']['ah']==[{'predicate':{'open_source':['tok:8:15']},
        'roles':{'SUBJECT':{'entity':'alexey'},'OBJECT':{'entity':'book'}}}]


def test_v2_gold_keeps_old_artifacts_and_requires_contract():
    from tools.check_formalizer_v7_oracle import load_corpus,evaluate
    root=Path(__file__).resolve().parents[1]/'data'
    old,old_cases=load_corpus(root/'formalizer_v7_oracle')
    new,new_cases=load_corpus(root/'formalizer_v7_oracle_v2')
    before=next(c for c in old_cases if c['case_id']=='OPEN-02-3-asserted')
    after=next(c for c in new_cases if c['case_id']==before['case_id'])
    expected=after['steps'][0]['checks'][0]['value']
    assert expected[0]['predicate']=={'open_source':['tok:8:15']}
    assert before['steps'][0]['checks'][0]['value'][0]['predicate']=='OPEN:флукнуть'
    guard=next(c for c in after['steps'][0]['checks'] if c['path']=='/observer/contract')
    assert not evaluate(guard,{'observer':{'contract':'v7-observer-1'}},{})
    assert not evaluate({'op':'set_eq','path':'/facts','value':expected},
        {'facts':[{'predicate':{'open_source':['tok:0:7']},'roles':expected[0]['roles']}]},{})


def test_numeric_and_json_workers_receive_their_own_format():
    from ah.formalizer.real_backend import RealBackendSelector
    from ah.formalizer.selection_prompt import SelectionPrompt
    captured=[]
    class Backend:
        def generate(self,prompt,**kwargs):captured.append(kwargs);return '1'
    prompt=SelectionPrompt('test',{'candidates':['a'],'protocol':'SELECT_LABELS_V1'})
    RealBackendSelector(Backend())._transport(prompt)
    RealBackendSelector(Backend(),selection_reply_format='JSON_V1')._transport(prompt)
    assert 'No explanation' in captured[0]['system']
    assert 'Reply ONLY with option numbers' not in captured[1]['system']
