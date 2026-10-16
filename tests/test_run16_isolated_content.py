"""Isolated probes receive the selected source, not an implicit conversation."""
from dataclasses import replace

import pytest

from test_structural_relation_tasks import run,relation,bounds,content_steps,atom,unary
from ah.formalizer.composition_tree import InputSlot


def test_nested_content_questions_name_the_actual_selected_body(tmp_path,monkeypatch):
    text='Иван сказал, что Пётр думал: «Мария пришла».'
    steps=relation('CONTENT')+bounds('structural_content','Мария','пришла')+bounds('structural_parent','Иван','думал')+[
        ('structural_function_owner','KEEP_ALL'),('structural_partition','PARTITION'),
        ('structural_owner','Content belongs to predicate «думал»'),
        ('structural_content_role','OBJECT:EMBEDDED')]
    steps+=content_steps('сказал','Пётр','думал')+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'predicate':'THINK','roles':{'AGENT':{'entity':'petr'},'CONTENT':atom('ARRIVE','maria')}}}}]
    for slot in ['structural_parent_start','structural_parent_end','structural_owner','structural_content_role']:
        prompt=next(p for s,p in script.calls if s==slot)
        assert 'Selected dependent content: «Мария пришла»' in prompt
        assert 'Context span: '+text in prompt
    owner=next(p for s,p in script.calls if s=='structural_owner')
    assert 'Remaining parent: «Иван сказал , что Пётр думал»' in owner
    role=next(p for s,p in script.calls if s=='structural_content_role')
    assert 'Selected owner: «думал»' in role
    function=next(p for s,p in script.calls if s=='structural_function_owner')
    assert 'this word introduces the selected content «Мария пришла»' in function
    prompts=[p for s,p in script.calls if s=='structural_relation']
    assert 'Only «думал»' in prompts[1] and '— «Мария пришла»' in prompts[1]
    assert 'Only «сказал»' in prompts[2] and '— «Пётр думал»' in prompts[2]
    assert 'Only «думал»' in prompts[3] and '— «Мария пришла»' in prompts[3]


def test_quoted_adjective_and_infinitive_do_not_inherit_the_speaker(tmp_path,monkeypatch):
    steps=content_steps('сказал','Мария','спать')+[
        ('structural_control','INDEPENDENT_CONTENT')]+relation('LEXICAL')+[
        ('component_attachment','Infinitive area «спать»')]+relation('LEXICAL')+[
        ('component_attachment','готовый [ADJS]'),
        ('component_attachment','«спать» fills OBJECT')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван сказал: «Мария готова спать».',steps)
    assert result['diagnostics']['codes']==[]
    content=result['assertions']['ah'][0]['roles']['CONTENT']
    assert content['roles']['AGENT']=={'entity':'maria'}
    assert content['roles']['CONTENT']==atom('SLEEP','maria')
    prompt=next(p for s,p in script.calls if s=='structural_control')
    assert 'Parent: «Иван сказал»' in prompt and 'Content: «Мария готова спать»' in prompt
    children=[p for s,p in script.calls if s=='structural_relation'][2:]
    assert 'No subject is inherited' in children[0]
    frames=result['runtime']['ir']['frames']
    sleep=next(f for f in frames if f['anchor_span']=='спать' and f['semantic'].get('candidate_specs'))
    refs=sleep['semantic']['control_binding']
    assert refs['token_ref']=='tok:14:19'


@pytest.mark.parametrize('answer',['?','0'])
def test_unresolved_control_does_not_guess_a_speaker(tmp_path,monkeypatch,answer):
    steps=content_steps('сказал','Мария','спать')+[('structural_control',answer)]
    if answer=='0':steps+=[('structural_revision','DEFER')]
    result,_=run(tmp_path,monkeypatch,'Иван сказал: «Мария готова спать».',steps)
    assert not result['assertions']['ah'] and not result['assertions']['journal']


def test_boundary_remainder_is_recorded_for_gui_without_changing_the_model_options(tmp_path,monkeypatch):
    steps=unary('NOT','не','не')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван не прочитал книгу.',steps)
    assert result['diagnostics']['codes']==[]
    prompt=next(p for s,p in script.calls if s=='structural_introducer_end')
    assert 'content left for this relation' not in prompt and 'beside each endpoint' not in prompt
    trace=next(r for r in result['runtime']['ir']['syntax_trace']
               if r.get('kind')=='STRUCTURAL_TASK' and r.get('slot')=='structural_introducer_end')
    selected=next(v for v in trace['alternatives'] if v['candidate_id']==trace['selected'])
    assert selected['selected_refs']==['tok:5:7']
    assert selected['remainder_refs']==['tok:0:4','tok:8:16','tok:17:22','tok:22:23']


def test_marker_question_is_about_one_word_and_keeps_a_rejection(tmp_path,monkeypatch):
    steps=relation('NOT')+bounds('structural_introducer','Не','не')+[
        ('relation_marker_role','«каждый»'),('structural_introducer_start','?')]
    result,script=run(tmp_path,monkeypatch,'Не каждый студент мог не сдать экзамен.',steps)
    assert not result['assertions']['ah']
    prompt=next(p for s,p in script.calls if s=='relation_marker_role')
    assert 'Question about ONE source word: «каждый»' in prompt
    assert 'All these words' not in prompt and 'An action remains content even when it is negated' in prompt


def test_changed_separated_content_invalidates_the_common_probe_cache():
    from test_composition_dispatcher import setup_morphology,First
    from ah.formalizer.composition_session import session
    from ah.formalizer.structural_tasks import choose
    state,release,region,cfg=setup_morphology('Иван сказал, что Пётр думал: «Мария пришла».')
    by_word={t.span:t for t in state.evidence}
    owner=by_word['думал'];selector=First()
    slot=InputSlot(
        pending_propositions={owner.token_id:frozenset({'OBJECT'})})
    with session(state,release,selector=selector) as runtime:
        def ask(words):
            request=replace(slot,pending_proposition_sources={owner.token_id:tuple(by_word[w].token_id for w in words)})
            with runtime.area(region,state.evidence,request):
                return runtime.dispatcher.run('content-producer',request,
                    lambda:choose(state,release,selector,region,cfg,'source-check',
                        [{'candidate_id':'yes','label':'Retain this source attachment'}],'Is this attachment supported?'),
                    kind='COMPOSITION')
        ask(['Мария','пришла']);ask(['Мария','пришла'])
        assert len(selector.prompts)==1
        ask(['пришла'])
        assert len(selector.prompts)==2 and '— «пришла»' in selector.prompts[-1]
        assert any(r.get('kind')=='DISPATCH_INVALIDATED' for r in state.syntax_trace)


def test_known_desire_role_is_consistent_in_all_observers(tmp_path,monkeypatch):
    steps=relation('LEXICAL')+[('component_attachment','Infinitive area')]+relation('LEXICAL')+[
        ('component_attachment','«читать» fills OBJECT')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Иван хочет читать книгу.',steps)
    expected={'predicate':'WANT','roles':{'EXPERIENCER':{'entity':'ivan'},'CONTENT':{
        'predicate':'READ','roles':{'AGENT':{'entity':'ivan'},'THEME':{'entity':'book'}}}}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert expected in result['generation']['observed_candidate_patterns']


def test_independent_content_clears_an_ancestor_infinitive_controller(tmp_path,monkeypatch):
    text='Иван решил сказать: «Мария готова спать».'
    steps=content_steps('решил','сказать','спать',attitude='HYPOTHETICAL')+[
        ('structural_control','Same SUBJECT')]
    steps+=content_steps('сказать','Мария','спать',parent_first='сказать')+[
        ('structural_control','INDEPENDENT_CONTENT')]+relation('LEXICAL')+[
        ('component_attachment','Infinitive area «спать»')]+relation('LEXICAL')+[
        ('component_attachment','готовый [ADJS]'),
        ('component_attachment','«спать» fills OBJECT')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    say=result['assertions']['ah'][0]['roles']['CONTENT']
    assert say['predicate']=='SAY' and say['roles']['AGENT']=={'entity':'ivan'}
    assert say['roles']['CONTENT']['roles']['CONTENT']==atom('SLEEP','maria')
