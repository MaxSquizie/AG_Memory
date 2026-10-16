"""Lost parent material, inherited control and typed observation regressions."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_structural_relation_tasks import run,relation,bounds,content_steps,atom


@pytest.mark.parametrize('revise',[False,True])
def test_content_partition_cannot_discard_an_outer_speaker(tmp_path,monkeypatch,revise):
    text='Иван сказал, что Пётр думал: «Мария пришла».'
    bad=relation('CONTENT')+bounds('structural_content','Мария','пришла')+bounds('structural_parent','Пётр','думал')
    steps=bad
    if revise:
        steps+=content_steps('сказал','Пётр','пришла')[1:]+content_steps('думал','Мария','пришла','Пётр','EMBEDDED')+relation('LEXICAL')
    else:steps+=[('structural_content_start','?')]
    result,script=run(tmp_path,monkeypatch,text,steps)
    conflicts=[r for r in result['runtime']['ir']['syntax_trace'] if r.get('kind')=='STRUCTURAL_PARTITION_COVERAGE']
    assert conflicts and conflicts[0]['uncovered_token_refs']==['tok:0:4','tok:5:11']
    if revise:
        assert result['diagnostics']['codes']==[]
        assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
            'CONTENT':{'predicate':'THINK','roles':{'AGENT':{'entity':'petr'},'CONTENT':atom('ARRIVE','maria')}}}}]
    else:
        assert not result['assertions']['ah'] and not result['assertions']['journal']
        assert 'STRUCTURAL_CONTENT_UNCOVERED' in result['diagnostics']['codes']
        assert not any(slot=='structural_partition' for slot,_ in script.calls)
    assert not any(s=='structural_revision' for s,_ in script.calls)
    revised=[p for s,p in script.calls if s=='structural_content_start'][1]
    assert 'local ownership check keeps «Иван» @0, «сказал» @5 in the content' in revised


@pytest.mark.parametrize('text,owner,attitude,parent,person',[
    ('Иван разрешил Петру спать.','разрешил','UNKNOWN','Иван','petr'),
    ('Мария просит Ивана спать.','просит','HYPOTHETICAL','Мария','ivan'),
])
def test_oblique_controller_reaches_known_infinitive_valency(tmp_path,monkeypatch,text,owner,attitude,parent,person):
    recipient='Петру' if person=='petr' else 'Ивана'
    steps=relation('CONTENT')+bounds('structural_content','спать','спать')+bounds('structural_parent',parent,recipient)+[
        ('structural_partition','PARTITION'),('structural_owner','Content belongs to predicate «'+owner+'»'),
        ('structural_content_role','OBJECT:'+attitude)]+relation('LEXICAL')+[
        ('structural_control','Same RECIPIENT')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    facts=result['assertions']['ah'];assert len(facts)==1
    assert facts[0]['roles']['CONTENT']==atom('SLEEP',person)
    frames=result['runtime']['ir']['frames']
    child=next(f for f in frames if f['anchor_span']=='спать' and f['semantic'].get('candidate_specs'))
    binding=child['semantic']['control_binding']
    assert binding['child_role']=='SUBJECT' and binding['role']=='RECIPIENT'
    assert child['semantic']['morph_bindings'][binding['token_ref']]['cases']==['dat' if person=='petr' else 'acc']


def test_control_exception_requires_the_actual_parent_binding():
    from test_composition_dispatcher import setup_morphology
    from ah.formalizer.component_policy import _morph
    from ah.formalizer.control_arguments import bind,controllers
    from ah.formalizer.native_frontend import _bindings
    state,release,_,_=setup_morphology('Петру спать.')
    person,predicate=state.evidence[:2]
    parent=SimpleNamespace(frame_id='parent',semantic={'proposed_roles':{person.token_id:'RECIPIENT'},
        'morph_bindings':{person.token_id:_morph(person.variants[0])},
        'lexical_units':{person.token_id:{'head_ref':person.token_id,'anchor_refs':[person.token_id],'surface':person.span}}})
    alias=next(controllers(parent))[0]
    sem={'proposed_roles':{},'morph_bindings':{predicate.token_id:_morph(predicate.variants[0])},'lexical_units':{}}
    bind(sem,alias,'SUBJECT')
    child=SimpleNamespace(construction='COMPONENTS_V1',semantic=sem,predicate_token_ref=predicate.token_id,
        argument_token_refs=[person.token_id],source_range=(predicate.start,predicate.end))
    evidence={t.token_id:t for t in state.evidence}
    valency=next(v for v in release.entries('R-V') if v['sense_id']=='SLEEP')
    assert _bindings(child,evidence,valency,parents={'parent':parent})==[{person.token_id:'SUBJECT'}]
    assert _bindings(child,evidence,valency,parents={})==[]
    changed=deepcopy(parent);changed.semantic['proposed_roles'][person.token_id]='OBJECT'
    assert _bindings(child,evidence,valency,parents={'parent':changed})==[]


def test_departure_without_named_origin_does_not_require_an_invented_place(tmp_path,monkeypatch):
    steps=relation('LEXICAL')+[('component_attachment','Infinitive area «уехать.')]+relation('LEXICAL')+[
        ('component_attachment','намеренный [ADJS]'),('component_attachment','«уехать» fills OBJECT')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Пётр намерен уехать.',steps)
    assert result['diagnostics']['codes']==[]
    child=result['assertions']['ah'][0]['roles']['CONTENT']
    assert child=={'predicate':'DEPART_CITY','roles':{'AGENT':{'entity':'petr'}}}


def test_open_content_alias_uses_argument_type_in_all_observations(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Иван начал читать книгу.',relation('LEXICAL')+[
        ('component_attachment','Infinitive area')]+relation('LEXICAL')+[
        ('component_attachment','«читать» fills OBJECT')]+relation('LEXICAL'))
    expected={'predicate':'OPEN:начать','roles':{'AGENT':{'entity':'ivan'},'CONTENT':{
        'predicate':'READ','roles':{'AGENT':{'entity':'ivan'},'THEME':{'entity':'book'}}}}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert expected in result['generation']['observed_candidate_patterns']


@pytest.mark.parametrize('text,predicate,person',[
    ('Мне холодно.','холодно','speaker'),('Петру жарко.','жарко','petr'),
])
def test_impersonal_state_has_dative_experiencer_and_no_invented_subject(tmp_path,monkeypatch,text,predicate,person):
    result,script=run(tmp_path,monkeypatch,text,relation('LEXICAL')+[
        ('component_attachment',predicate+' [ADVB]')])
    expected={'predicate':'OPEN:'+predicate,'roles':{'EXPERIENCER':{'entity':person}}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert result['diagnostics']['codes']==[]
    assert any('impersonal state; dative participant experiences it' in p for _,p in script.calls)
    # Rejected adjective readings remain inspectable, without a false global error.
    assert any(t.get('kind')=='DEPENDENCY_REJECTED' for t in result['runtime']['ir']['syntax_trace'])


def test_impersonal_experiencer_can_control_known_infinitive(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Мне хочется спать.',relation('LEXICAL')+[
        ('component_attachment','Infinitive area')]+relation('LEXICAL')+[
        ('component_attachment','хотеться [VERB]'),('component_attachment','«спать» fills OBJECT')]+relation('LEXICAL'))
    expected={'predicate':'OPEN:хотеться','roles':{'EXPERIENCER':{'entity':'speaker'},
        'CONTENT':atom('SLEEP','speaker')}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert result['diagnostics']['codes']==[]
    frames=result['runtime']['ir']['frames']
    parent=next(f for f in frames if f['anchor_span']=='хочется' and f['semantic'].get('candidate_specs'))
    child=next(f for f in frames if f['anchor_span']=='спать' and f['semantic'].get('candidate_specs'))
    assert not parent['semantic'].get('implicit_arguments')
    assert child['semantic']['control_binding']['role']=='EXPERIENCER'


def test_impersonal_reading_can_be_rejected_without_a_fabricated_fact(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Мне холодно.',relation('LEXICAL')+[
        ('component_attachment','0'),('structural_revision','DEFER')])
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    assert 'COMPONENT_DEPENDENCY_CONTRADICTION' in result['diagnostics']['codes']


@pytest.mark.parametrize('text,dependent,kind',[
    ('Иван, врач думает.','врач','APPOSITION'),
    ('Иван книгу читает.','книгу','CASE_DEPENDENCY'),
])
@pytest.mark.parametrize('answer',['1','0','?'])
def test_single_semantic_attachment_is_a_proposal_not_a_deterministic_fact(text,dependent,kind,answer):
    from test_composition_dispatcher import setup_morphology,First
    from ah.formalizer.component_dependency_reduction import reduce
    state,release,region,cfg=setup_morphology(text)
    tokens=list(state.evidence)
    host=next(t for t in tokens if t.span=='Иван')
    child=next(t for t in tokens if t.span==dependent)
    predicate=next(t for t in tokens if any(v.pos=='VERB' for v in t.variants))
    reading=next(v for v in predicate.variants if v.pos=='VERB')
    selector=First(answer)
    result=reduce(state,release,selector,region,tokens,predicate,reading,
        [{'role_id':'SUBJECT','allowed_cases':['nom'],'cardinality':{'min':1,'max':1}}],
        [host,child],{},cfg,required_roots={host.token_id:'SUBJECT'})
    assert len(selector.prompts)==1 and kind in selector.prompts[0]
    assert '2. ' not in selector.prompts[0]
    assert text in selector.prompts[0]
    if answer=='1':
        assert result['dependencies'][0]['kind']==kind
        chosen=next(t for t in result['trace'] if t['token_ref']==child.token_id)
        assert chosen['ground']=='M'
    else:
        assert result is None
