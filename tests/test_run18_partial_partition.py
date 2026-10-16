"""A partial split can supply ownership evidence without licensing a fact."""
import pytest
from test_structural_relation_tasks import run,relation,bounds,atom
from test_run15_boundary_ownership import parent_tail,content_link


@pytest.mark.parametrize('quoted',[False,True])
def test_all_words_in_marker_can_reopen_content_before_child_composition(tmp_path,monkeypatch,quoted):
    text='Иван не пришёл.'
    steps=[]
    if quoted:
        text='Пётр сказал: «Иван не пришёл».'
        steps=relation('CONTENT')+bounds('structural_content','Иван','пришёл')+bounds('structural_parent','Пётр','сказал')+[
            ('structural_partition','PARTITION'),('structural_owner','Content belongs to predicate «сказал»'),
            ('structural_content_role','OBJECT:QUOTED')]+relation('LEXICAL')
    steps+=relation('NOT')+bounds('structural_introducer','Иван','пришёл')+[
        ('relation_marker_role','«Иван»')]+bounds('structural_introducer','не','не')+[
        ('structural_partition','PARTITION')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,text,steps)
    expected={'operator':'NOT','operands':[atom('ARRIVE','ivan')]}
    if quoted:expected={'predicate':'SAY','roles':{'AGENT':{'entity':'petr'},'CONTENT':expected}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert result['diagnostics']['codes']==[]
    marker=next(p for s,p in script.calls if s=='relation_marker_role')
    assert 'Content parts: none retained.' in marker
    assert 'already names what this relation applies to' not in marker
    assert not any(s=='structural_revision' for s,_ in script.calls)


def test_quantifier_cannot_swallow_its_entire_restriction_and_body(tmp_path,monkeypatch):
    steps=relation('FORALL')+bounds('structural_quantifier','Каждый','книгу')+[
        ('relation_marker_role','RELATION_ONLY'),('relation_marker_role','«студент»')]
    steps+=bounds('structural_quantifier','Каждый','Каждый')+[
        ('structural_partition','PARTITION'),('structural_binder_head','Bind the nominal «студент»')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Каждый студент читает книгу.',steps)
    assert result['diagnostics']['codes']==[]
    assert len(result['assertions']['ah'])==1 and result['assertions']['ah'][0]['operator']=='FORALL'
    assert result['assertions']['ah'][0]['operands'][1]['operands'][1]['predicate']=='READ'


@pytest.mark.parametrize('answer',['?','RELATION_ONLY'])
def test_empty_content_remains_unassertible_when_no_conflict_is_established(tmp_path,monkeypatch,answer):
    steps=relation('POSSIBLE')+bounds('structural_introducer','Можно','предположить')+[('relation_marker_role',answer)]
    if answer=='RELATION_ONLY':steps+=[('structural_revision','DEFER')]
    result,script=run(tmp_path,monkeypatch,'Можно предположить.',steps)
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    assert not any(s=='structural_partition' for s,_ in script.calls)
    assert len([s for s,_ in script.calls if s=='structural_introducer_start'])==1


def test_parent_question_distinguishes_predicate_from_connecting_conjunction(tmp_path,monkeypatch):
    steps=parent_tail('сказала','Иван','пришёл','Мария','сказала')+content_link('сказала')+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Мария сказала: «Иван пришёл».',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'maria'},'CONTENT':atom('ARRIVE','ivan')}}]
    for slot in ('structural_parent_start','structural_parent_end'):
        prompt=next(p for s,p in script.calls if s==slot)
        assert 'Selected dependent content: «Иван пришёл»' in prompt
        assert 'the predicate that takes this content, its participants and other attached clauses' in prompt
        assert 'Boundary punctuation may stay' in prompt
        assert 'introducer of THIS content' not in prompt


def test_parent_reduced_to_only_punctuation_still_reaches_coverage_repair(tmp_path,monkeypatch):
    steps=parent_tail('сказала','Иван','пришёл',':',':')
    steps+=bounds('structural_content','Иван','пришёл')+bounds('structural_parent','Мария','сказала')
    steps+=content_link('сказала')+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Мария сказала: «Иван пришёл».',steps)
    expected={'predicate':'SAY','roles':{'AGENT':{'entity':'maria'},'CONTENT':atom('ARRIVE','ivan')}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert result['diagnostics']['codes']==[]
    assert not any(s=='structural_revision' for s,_ in script.calls)
    rows=result['runtime']['ir']['syntax_trace']
    conflict=next(r for r in rows if r.get('kind')=='STRUCTURAL_PARTITION_COVERAGE')
    assert conflict['status']=='REPAIRED' and conflict['uncovered_token_refs']==['tok:0:5','tok:6:13']
