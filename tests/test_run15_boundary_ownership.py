"""Broad recorded parent spans, punctuation ownership and lexical marker loss."""
import pytest

from test_structural_relation_tasks import run,relation,bounds,content_steps,atom


def parent_tail(owner,first,last,parent_first,parent_last,attitude='QUOTED'):
    return relation('CONTENT')+bounds('structural_content',first,last)+bounds('structural_parent',parent_first,parent_last)


def content_link(owner,attitude='QUOTED'):
    return [('structural_partition','PARTITION'),('structural_owner','Content belongs to predicate «'+owner+'»'),
        ('structural_content_role','OBJECT:'+attitude)]


@pytest.mark.parametrize('opening,closing',[('«','»'),('“','”'),('"','"')])
def test_parent_span_can_include_closed_quote_shell_without_owning_its_content(tmp_path,monkeypatch,opening,closing):
    text='Мария сказала: '+opening+'Иван пришёл'+closing+'.'
    steps=parent_tail('сказала','Иван','пришёл','Мария',closing)+content_link('сказала')+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,text,steps)
    expected={'predicate':'SAY','roles':{'AGENT':{'entity':'maria'},'CONTENT':atom('ARRIVE','ivan')}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert result['diagnostics']['codes']==[]
    trace=next(r for r in result['runtime']['ir']['syntax_trace'] if r.get('kind')=='CONTENT_SEPARATOR_OWNERSHIP')
    assert trace['status']=='CONFIRMED' and trace['decision_ref']
    partition=next(p for slot,p in script.calls if slot=='structural_partition')
    assert 'parent clause with a content slot: «Мария сказала»' in partition
    assert 'Context span: '+text in partition


def test_broad_parent_with_conjunction_requires_its_own_occurrence_choice(tmp_path,monkeypatch):
    steps=parent_tail('сказал','Пётр','пришёл','Иван','.')+[
        ('structural_function_owner','Outer relation owns «что»')]+content_link('сказал')+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван сказал, что Пётр пришёл.',steps)
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},'CONTENT':atom('ARRIVE','petr')}}]
    assert result['diagnostics']['codes']==[]
    question=next(p for s,p in script.calls if s=='structural_function_owner')
    assert 'Part 1 is the parent, part 2 is its selected content' in question


def test_nested_parent_keeps_its_inner_conjunction_and_speaker(tmp_path,monkeypatch):
    text='Иван сказал, что Пётр думал: «Мария пришла».'
    steps=parent_tail('думал','Мария','пришла','Иван','.')+[
        ('structural_function_owner','KEEP_ALL')]+content_link('думал','EMBEDDED')
    steps+=content_steps('сказал','Пётр','думал')+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'predicate':'THINK','roles':{'AGENT':{'entity':'petr'},'CONTENT':atom('ARRIVE','maria')}}}}]
    partition=next(p for slot,p in script.calls if slot=='structural_partition')
    assert 'parent clause with a content slot: «Иван сказал , что Пётр думал»' in partition


def test_punctuation_proposal_does_not_override_rejected_partition(tmp_path,monkeypatch):
    steps=parent_tail('сказала','Иван','пришёл','Мария','»')+[
        ('structural_partition','0'),('structural_revision','DEFER')]
    result,_=run(tmp_path,monkeypatch,'Мария сказала: «Иван пришёл».',steps)
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    trace=next(r for r in result['runtime']['ir']['syntax_trace'] if r.get('kind')=='CONTENT_SEPARATOR_OWNERSHIP')
    assert trace['status']=='UNCONFIRMED'


@pytest.mark.parametrize('text,body_words',[
    ('Иван сказал: «Пётр пришёл и Мария спит».',{'Пётр','пришёл'}),
    ('Иван сказал: «Пётр пришёл.',{'Пётр','пришёл'}),
    ('Иван сказал: «Пётр пришёл?».',{'Пётр','пришёл'}),
])
def test_delimiters_are_not_consumed_when_body_leaves_other_scope_material(text,body_words):
    from test_composition_dispatcher import setup_morphology
    from ah.formalizer.content_separators import separate
    state,_,region,_=setup_morphology(text)
    tokens=list(state.evidence);body=[t for t in tokens if t.span in body_words]
    parent=[t for t in tokens if t not in body]
    proposed,_=separate(state,region,tokens,parent,body)
    assert next(t.token_id for t in tokens if t.span=='«') in {t.token_id for t in proposed}
    if '?' in text:assert any(t.span=='?' for t in proposed)


@pytest.mark.parametrize('answer',['«прочитать»','?'])
def test_modal_marker_cannot_discard_an_action_after_probe_rejects_its_role(tmp_path,monkeypatch,answer):
    steps=relation('POSSIBLE')+bounds('structural_introducer','можно','прочитать')+[
        ('relation_marker_role',answer)]
    if answer!='?':steps+=[('structural_introducer_start','?')]
    result,script=run(tmp_path,monkeypatch,'Книгу можно прочитать.',steps)
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    assert not any(s=='structural_event_head' for s,_ in script.calls)
    prompt=next(p for s,p in script.calls if s=='relation_marker_role')
    assert 'Words assigned to it: «можно прочитать»' in prompt
    assert 'Content parts: «Книгу»' in prompt
    if answer!='?':assert 'STRUCTURAL_MARKER_CONTENT' in result['diagnostics']['codes']


def test_infinitive_can_still_express_a_relation_when_its_role_is_confirmed(tmp_path,monkeypatch):
    # Infinitive morphology alone cannot prohibit a lexical modal expression.
    steps=relation('POSSIBLE')+bounds('structural_introducer','Можно',':')+[
        ('relation_marker_role','RELATION_ONLY'),('structural_partition','PARTITION')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Можно предположить: Иван пришёл.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'operator':'POSSIBLE','operands':[atom('ARRIVE','ivan')]}]


def test_revising_a_marker_restores_the_action_under_negation(tmp_path,monkeypatch):
    steps=relation('NOT')+bounds('structural_introducer','не','прочитал')+[
        ('relation_marker_role','«прочитал»')]
    steps+=bounds('structural_introducer','не','не')+[
        ('structural_partition','PARTITION')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван не прочитал книгу.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'operator':'NOT','operands':[{
        'predicate':'READ','roles':{'AGENT':{'entity':'ivan'},'THEME':{'entity':'book'}}}]}]
    assert not any(s=='structural_revision' for s,_ in script.calls)
    revised=[p for s,p in script.calls if s=='structural_introducer_start'][1]
    assert 'local ownership check keeps «прочитал» @8 in the content' in revised
    assert 'Start at «прочитал»' not in revised
