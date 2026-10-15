"""Noun predicates stay reachable and require a source-grounded selection."""
import pytest

from test_structural_relation_tasks import run,relation,unary,content_steps


@pytest.mark.parametrize('text,person',[
    ('Иван — врач.','ivan'),('Мария врач.','maria'),
    ('Мария была врачом.','maria'),('Иван был врач.','ivan'),
])
def test_nominal_predicate_uses_subject_and_copula_agreement(tmp_path,monkeypatch,text,person):
    result,script=run(tmp_path,monkeypatch,text,relation('LEXICAL')+[
        ('component_attachment','врач [NOUN]')])
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'DOCTOR','roles':{'THEME':{'entity':person}}}]
    prompts=[p for s,p in script.calls if s=='component_attachment']
    assert any('noun predicate:' in p for p in prompts)


def test_nominal_predicate_under_question_is_not_forced_to_be_event_noun(tmp_path,monkeypatch):
    steps=unary('QUERY','Верно','что')+[('structural_event_head','PROPOSITION')]+relation('LEXICAL')+[
        ('component_attachment','врач [NOUN]')]
    result,_=run(tmp_path,monkeypatch,'Верно ли, что Иван — врач?',steps,kind='QUERY')
    assert result['diagnostics']['codes']==['SPEECH_ACT_QUERY']
    assert not result['assertions']['ah']
    assert {'predicate':'DOCTOR','roles':{'THEME':{'entity':'ivan'}}} in result['generation']['observed_candidate_patterns']


def test_reported_nominal_predicate_is_only_content(tmp_path,monkeypatch):
    steps=content_steps('сказал','Мария','врач')+[('structural_event_head','PROPOSITION')]+relation('LEXICAL')+[
        ('component_attachment','врач [NOUN]')]
    result,_=run(tmp_path,monkeypatch,'Иван сказал, что Мария врач.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'predicate':'DOCTOR','roles':{'THEME':{'entity':'maria'}}}}}]


@pytest.mark.parametrize('text',['Мария врачом.','Мария был врачом.','Врач.'])
def test_incomplete_or_mismatched_nominal_predication_cannot_assert(tmp_path,monkeypatch,text):
    result,_=run(tmp_path,monkeypatch,text,relation('LEXICAL')+[('structural_revision','DEFER')])
    assert not result['assertions']['ah']


def test_model_can_reject_nominal_predication(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Иван — врач.',relation('LEXICAL')+[
        ('component_attachment','0'),('structural_revision','DEFER')])
    assert not result['assertions']['ah']
