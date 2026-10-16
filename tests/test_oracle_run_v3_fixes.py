"""General source ownership and accepted-query regressions; no live model."""
from pathlib import Path
from test_structural_relation_tasks import run,relation,bounds,unary,content_steps


def test_content_owner_is_selected_before_partition_and_cannot_be_removed(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Иван сказал, что Пётр пришёл.',
        content_steps('сказал','Пётр','пришёл')+relation('LEXICAL'),observer_contract='v7-observer-3')
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'predicate':'ARRIVE','roles':{'AGENT':{'entity':'petr'}}}}}]
    slots=[slot for slot,prompt in script.calls]
    assert slots.index('structural_owner')<slots.index('structural_partition')
    assert all('Outer relation owns «сказал»' not in prompt for slot,prompt in script.calls if slot=='structural_function_owner')


def test_nominal_relation_preserves_its_complement_and_outer_subject(tmp_path,monkeypatch):
    steps=relation('LEXICAL')+[('nominal_function','An adposition')]
    steps+=bounds('nominal_function_source','из','из')+[
        ('nominal_function_head','Nominal head «Москвы»'),('nominal_function','0')]
    result,script=run(tmp_path,monkeypatch,'Иван уехал из Москвы.',steps,observer_contract='v7-observer-3')
    assert result['assertions']['ah']==[{'predicate':'DEPART_CITY',
        'roles':{'AGENT':{'entity':'ivan'},'SOURCE':{'entity':'moscow'}}}]
    head_prompt=next(p for s,p in script.calls if s=='nominal_function_head')
    assert 'selected function expression is «из»' in head_prompt


def test_impersonal_experiencer_is_not_forced_into_subject(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Мне холодно.',relation('LEXICAL')+[
        ('predicate_function','Predicate occurrence «холодно»'),
        ('predicate_argument_role','oblique or impersonal participant')],observer_contract='v7-observer-3')
    assert result['assertions']['ah']==[{'predicate':{'open_source':['tok:4:11']},'roles':{'EXPERIENCER':{'entity':'speaker'}}}]


def test_query_requires_a_compiled_selected_root(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Верно ли, что Пётр читает книгу?',
        unary('QUERY','Верно','что')+relation('LEXICAL'),kind='QUERY',observer_contract='v7-observer-3')
    assert result['assertions']['ah']==[]
    assert result['query']['status']=='COMPILED',result['query']
    assert result['query']['formulas']==[{'predicate':'READ',
        'roles':{'AGENT':{'entity':'petr'},'THEME':{'entity':'book'}}}]


def test_query_with_unfinished_structure_is_blocked_even_when_host_says_query(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Верно ли, что Иван пришёл?',unary('QUERY','Верно','что')+relation('LEXICAL')+[
        ('nominal_function','?')],kind='QUERY',observer_contract='v7-observer-3')
    assert result['modus']=='QUERY' and not result['assertions']['ah']
    assert result['query']['status']=='BLOCKED' and not result['query']['formulas']


def test_open_query_preserves_source_occurrence_through_compilation(tmp_path,monkeypatch):
    text='Верно ли, что мне холодно?'
    result,_=run(tmp_path,monkeypatch,text,unary('QUERY','Верно','что')+relation('LEXICAL')+[
        ('predicate_function','Predicate occurrence «холодно»'),
        ('predicate_argument_role','oblique or impersonal participant')],kind='QUERY',observer_contract='v7-observer-3')
    start=text.index('холодно')
    assert result['query']['status']=='COMPILED',result['query']
    assert result['query']['formulas']==[{'predicate':{'open_source':[f'tok:{start}:{start+7}']},
        'roles':{'EXPERIENCER':{'entity':'speaker'}}}]
    assert not result['assertions']['ah']


def test_v3_queries_have_exact_roots_not_only_candidate_checks():
    from tools.check_formalizer_v7_oracle import validate,load_corpus
    root=Path(__file__).resolve().parents[1]/'data'
    validate(root/'formalizer_v7_oracle_v3')
    _,cases=load_corpus(root/'formalizer_v7_oracle_v3')
    question=next(c for c in cases if c['case_id']=='NONFINITE-00-question')['steps'][0]
    check=next(c for c in question['checks'] if c['path']=='/query/formulas')
    assert len(check['value'])==1 and check['value'][0]['predicate']=='WANT'
    assert check['value'][0]['roles']['CONTENT']['predicate']=='READ'
