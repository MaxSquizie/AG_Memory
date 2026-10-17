"""Action descriptions travel through the actual GUI/native write boundary."""
import pytest
from test_structural_relation_tasks import run,relation,unary,content_steps


@pytest.mark.parametrize('text,kind,marker,governor,predicate,theme',[
    ('Книгу можно прочитать.','POSSIBLE','можно',None,'READ','book'),
    ('Нужно открыть окно.','NECESSARY','Нужно','INDEPENDENT','OPEN','window'),
    ('Книга может быть прочитана.','POSSIBLE','может','Agreement/controller anchor «может»','READ','book'),
    ('Окно может быть открыто.','POSSIBLE','может','Agreement/controller anchor «может»','OPEN','window'),
])
def test_unassigned_actor_is_not_an_entity_or_a_fact(tmp_path,monkeypatch,text,kind,marker,governor,predicate,theme):
    steps=unary(kind,marker,marker)
    if governor:steps+=[('structural_governor',governor)]
    steps+=relation('LEXICAL')
    if 'прочитана' in text:steps+=[('predicate_function','Predicate occurrence «прочитана»')]
    elif 'открыто' in text:steps+=[('predicate_function','Predicate occurrence «открыто»')]
    if 'прочитана' in text or 'открыто' in text:
        steps+=[('predicate_argument_role','core object')]
    if predicate=='OPEN' and 'открыто' in text:
        steps+=[('predicate_argument_reading','cases: nominative'),('component_attachment','unassigned participant slots: core subject')]
    result,script=run(tmp_path,monkeypatch,text,steps)
    expected={'operator':kind,'operands':[{'predicate':predicate,'roles':{'THEME':{'entity':theme}}}]}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]},result['diagnostics']
    assert result['diagnostics']['codes']==[]
    frames=[f for f in result['runtime']['ir']['frames'] if not f['semantic'].get('structural_unresolved')]
    assert len(frames)==1
    assert frames[0]['semantic']['action_description']['unassigned_roles']==['SUBJECT']
    assert not frames[0]['semantic'].get('implicit_arguments')
    assert not any(slot=='implicit_argument' for slot,_ in script.calls)
    assert any('action description; occurrence is NOT asserted' in p for s,p in script.calls if s=='component_attachment')


def test_quoted_description_does_not_inherit_the_speaker(tmp_path,monkeypatch):
    steps=content_steps('сказал','Книгу','прочитать')+[
        ('structural_control','INDEPENDENT_CONTENT')]+unary('POSSIBLE','можно','можно')+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Иван сказал: «Книгу можно прочитать».',steps)
    expected={'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},'CONTENT':
        {'operator':'POSSIBLE','operands':[{'predicate':'READ','roles':{'THEME':{'entity':'book'}}}]}}}
    assert result['assertions']=={'ah':[expected],'ir':[expected],'journal':[expected]}
    assert result['diagnostics']['codes']==[]


@pytest.mark.parametrize('text,governor,selection',[
    ('Ивану можно прочитать книгу.',None,None),
    ('Книга может быть прочитана Иваном.','Agreement/controller anchor «может»',None),
    ('Окно может быть открыто Марией.','Agreement/controller anchor «может»','открыть [short participle]'),
])
def test_explicit_actor_is_retained_without_patient_agreement(tmp_path,monkeypatch,text,governor,selection):
    marker='может' if governor else 'можно'
    steps=unary('POSSIBLE',marker,marker)
    if governor:steps+=[('structural_governor',governor)]
    steps+=relation('LEXICAL')
    if 'прочитана' in text:steps+=[('predicate_function','Predicate occurrence «прочитана»')]
    elif 'открыто' in text:steps+=[('predicate_function','Predicate occurrence «открыто»')]
    if governor:
        steps += [('predicate_argument_role','core object')]
        if 'открыто' in text:steps += [('predicate_argument_reading','cases: nominative')]
        steps += [('predicate_argument_role','core subject')]
    else:steps += [('predicate_argument_role','core subject'),('predicate_argument_role','core object')]
    if selection:steps+=[('component_attachment',selection)]
    result,_=run(tmp_path,monkeypatch,text,steps)
    action=result['assertions']['ah'][0]['operands'][0]
    assert action=={'predicate':'OPEN' if selection else 'READ','roles':{
        'AGENT':{'entity':'maria' if selection else 'ivan'},'THEME':{'entity':'window' if selection else 'book'}}}
    assert result['diagnostics']['codes']==[]


def ingest(session,monkeypatch,text,steps,source,kind='ASSERTION'):
    from test_structural_relation_tasks import Script
    from tools import formalizer_v7_native_binding as binding
    script=Script(steps);captured=[]
    original=binding.interpret_full
    def capture(*args,**kwargs):
        result=original(*args,**kwargs);captured.append(result[0]);return result
    with monkeypatch.context() as patch:
        patch.setattr(binding.ChatBackend,'generate',lambda self,prompt,**kw:script.generate(prompt,**kw))
        patch.setattr(binding,'interpret_full',capture)
        payload={'raw_input':{'text':text,'source_id':source,'revision':1,'range':[0,len(text)],
            'language':'ru','request_kind':kind,'batch_kind':'MESSAGE'}}
        result=binding.execute_native(session,payload,{'provider':'lmstudio','model':'action-description-test','structure_mode':'region_probes'})
    assert not script.errors and not script.steps,(script.errors,list(script.steps))
    return captured[0],result


def test_active_and_passive_query_the_same_property_without_asserting_occurrence(tmp_path,monkeypatch):
    from tools.formalizer_v7_extended_binding import Session
    from ah.formalizer.native_queries import project_native_queries,compile_native_queries,Pattern,QueryVar
    from ah.inference.engine import InferenceEngine
    from ah.config import InferenceSettings
    from ah.inference.contracts import NativeFormulaGoal,NativeBindingGoal,LogicalStatus
    from ah.model import ActantRole
    from types import SimpleNamespace
    from dataclasses import replace
    session=Session([],tmp_path/'queries.log')
    state,result=ingest(session,monkeypatch,'Книгу можно прочитать.',
        unary('POSSIBLE','можно','можно')+relation('LEXICAL'),'fact')
    assert result['diagnostics']['codes']==[]
    roots=session.store.ledger.f_visible()
    assert len(roots)==1
    node=next(n for n in session.store.ledger.data['nodes'].values() if n.get('action_description'))
    assert node['uid'] not in roots
    assert set(session.core.store.get_template(node['template_ref']).roles)=={ActantRole.SUBJECT,ActantRole.OBJECT}
    assert set(node['actants'])=={'OBJECT'}
    assert session.core.store.get_hypernode(node['uid']).meta['action_description']=={'unassigned_roles':['SUBJECT']}
    query,result=ingest(session,monkeypatch,'Книга может быть прочитана?',
        unary('QUERY','?','?')+unary('POSSIBLE','может','может')+[('structural_governor','Agreement/controller anchor «может»')]+relation('LEXICAL')+[('predicate_function','Predicate occurrence «прочитана»'),('predicate_argument_role','core object')],'query','QUERY')
    assert len(session.store.ledger.f_visible())==1
    compiled=compile_native_queries(session.core,project_native_queries(query,session.release),
        SimpleNamespace(user_ref=None,self_ref=None))
    assert len(compiled)==1 and compiled[0].goal is not None,compiled
    engine=InferenceEngine(session.core,InferenceSettings(max_expanded_states=256))
    target=compiled[0].goal.goal.target
    before=session.store._codec.export(session.core)
    assert engine.solve(target).status==LogicalStatus.PROVED
    action=target.pattern.members[0]
    assert engine.solve(NativeFormulaGoal(action)).status==LogicalStatus.UNKNOWN
    known_actor=replace(action,actants=(*action.actants,(ActantRole.SUBJECT,session.core.ref('fixture:language:M:ivan'))))
    assert engine.solve(NativeFormulaGoal(Pattern('POSSIBLE',(known_actor,)))).status==LogicalStatus.UNKNOWN
    who=replace(action,actants=(*action.actants,(ActantRole.SUBJECT,QueryVar('SUBJECT'))))
    answer=engine.solve(NativeBindingGoal(Pattern('POSSIBLE',(who,)),('SUBJECT',),'WH'))
    assert answer.status==LogicalStatus.UNKNOWN
    assert session.store._codec.export(session.core)==before
    what=replace(action,actants=((ActantRole.OBJECT,QueryVar('OBJECT')),))
    answer=engine.solve(NativeBindingGoal(Pattern('POSSIBLE',(what,)),('OBJECT',),'WH'))
    assert answer.status==LogicalStatus.PROVED
    assert 'fixture:language:M:book' in str(answer.conclusion)
    session.store.retract_observation(state.source_uid,state.interpretation_version,trigger_ref='test:retract')
    assert engine.solve(target).status==LogicalStatus.UNKNOWN


def test_description_cannot_be_promoted_by_detaching_its_modal(tmp_path,monkeypatch):
    from tools.formalizer_v7_extended_binding import Session
    from ah.formalizer.native_plan import build_plan
    session=Session([],tmp_path/'guard.log')
    state,_=ingest(session,monkeypatch,'Книгу можно прочитать.',
        unary('POSSIBLE','можно','можно')+relation('LEXICAL'),'guard')
    frame=next(f for f in state.frames if not f.semantic.get('structural_unresolved'))
    for key in ('component_scope_tree','operator_forest','coordination_owner','component_child'):
        frame.semantic.pop(key,None)
    operations,fragments,diagnostics,_=build_plan(state,session.release,session.store)
    assert any('ACTION_DESCRIPTION_WITHOUT_SCOPE' in d for d in diagnostics)
    assert not fragments and not any(o.op_type=='ADD_ROOT_SUPPORT' for o in operations)
    from ah.formalizer.runtime_adapter import FormalizerAdapter
    adapter=FormalizerAdapter(object(),release=session.release)
    assert not adapter._to_perception_result(state).assertions


def test_action_without_named_participants_does_not_introduce_any(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Можно читать.',unary('POSSIBLE','Можно','Можно')+relation('LEXICAL'))
    assert result['assertions']['ah']==[{'operator':'POSSIBLE','operands':[{'predicate':'READ','roles':{}}]}]
    frame=next(f for f in result['runtime']['ir']['frames'] if not f['semantic'].get('structural_unresolved'))
    assert frame['semantic']['action_description']['unassigned_roles']==['OBJECT','SUBJECT']
    assert not frame['semantic'].get('implicit_arguments')


def test_nominative_syncretism_keeps_the_whole_infinitive_option(tmp_path,monkeypatch):
    steps=unary('POSSIBLE','можно','можно')+relation('LEXICAL')+[
        ('component_attachment','Whole target is one infinitive action description'),
        ('predicate_function','Predicate occurrence «прочитать»'),
        ('nominal_dependency','ATTRIBUTE dependency on «роман»'),
        ('predicate_argument_role','This occurrence belongs to another nominal'),
        ('predicate_argument_role','core object'),
        ('predicate_argument_reading','lemma: роман; pos: noun; cases: accusative')]
    result,_=run(tmp_path,monkeypatch,'Старый роман можно прочитать.',steps)
    assert result['diagnostics']['codes']==[]
    action=result['assertions']['ah'][0]['operands'][0]
    assert action['predicate']=='READ' and set(action['roles'])=={'THEME'}


@pytest.mark.parametrize('answer',['?','ONE_SELECTED'])
def test_unresolved_description_selection_does_not_materialize_a_fact(tmp_path,monkeypatch,answer):
    steps=unary('POSSIBLE','можно','можно')+relation('LEXICAL')+[('component_attachment',answer)]
    if answer=='?':steps+=[('child_slot','?')]
    result,_=run(tmp_path,monkeypatch,'Книгу можно прочитать.',steps)
    assert not result['assertions']['ah'] and not result['assertions']['journal']


def test_description_gui_names_unassigned_roles_without_raw_json(tmp_path,monkeypatch):
    from ah.gui.formalization_readable import ReadableInspection
    from ah.gui.formalization_inspection import Inspection
    result,_=run(tmp_path,monkeypatch,'Книгу можно прочитать.',unary('POSSIBLE','можно','можно')+relation('LEXICAL'))
    data={'source_text':'Книгу можно прочитать.','state':result['runtime']['ir']}
    idx=Inspection(data);reader=ReadableInspection(idx)
    frame=next(f for f in data['state']['frames'] if f['semantic'].get('action_description') and not f['semantic'].get('structural_unresolved'))
    html=reader.explain(idx.by_ref[frame['frame_id']])
    assert 'не факт его совершения' in html and 'Сущность не создаётся' in html
    assert 'action_description' not in html and 'unassigned_roles' not in html


def test_independent_inner_modal_clears_ancestral_agreement(tmp_path,monkeypatch):
    steps=unary('POSSIBLE','Возможно',',')+[('structural_governor','Agreement/controller anchor «Возможно»')]
    steps+=unary('NECESSARY','нужно','нужно')+[('structural_governor','INDEPENDENT')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Возможно, нужно открыть окно.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'operator':'POSSIBLE','operands':[
        {'operator':'NECESSARY','operands':[{'predicate':'OPEN','roles':{'THEME':{'entity':'window'}}}]}]}]
    frame=next(f for f in result['runtime']['ir']['frames'] if not f['semantic'].get('structural_unresolved'))
    assert frame['semantic']['agreement_source_ref'] is None
    assert not frame['semantic'].get('implicit_arguments')


def test_experience_retains_only_the_selected_morphological_reading(tmp_path,monkeypatch):
    from tools.formalizer_v7_extended_binding import Session
    session=Session([],tmp_path/'experience.log')
    state,result=ingest(session,monkeypatch,'Окно может быть открыто.',unary('POSSIBLE','может','может')+[
        ('structural_governor','Agreement/controller anchor «может»')]+relation('LEXICAL')+[
        ('predicate_function','Predicate occurrence «открыто»'),('predicate_argument_role','core object'),('predicate_argument_reading','cases: nominative'),('component_attachment','unassigned participant slots: core subject')],'experience')
    assert result['diagnostics']['codes']==[]
    stages=[row['stages'] for row in session.store.ledger.data['rx_cache'].values()]
    assert stages
    priors=[row for stage in stages for row in stage['T3']['semantic_priors']]
    assert priors==[{'lemma':'открыть','POS':'PRTS','sense_id':'OPEN_PRTS'}]
    morphology=[row for stage in stages for row in stage['T1']['morphological_priors']]
    assert morphology==[{'surface':'открыто','variants':[{'lemma':'открыть','POS':'PRTS'}]}]


def test_partial_description_cannot_bypass_a_missing_known_template(tmp_path,monkeypatch):
    from tools.formalizer_v7_extended_binding import Session
    from tools import formalizer_v7_native_binding as binding
    original=binding.fixture
    monkeypatch.setattr(binding,'fixture',lambda core,profile:original(core,'known_mapping_broken'))
    session=Session([],tmp_path/'missing-template.log')
    state,result=ingest(session,monkeypatch,'Письмо можно отправить.',
        unary('POSSIBLE','можно','можно')+relation('LEXICAL'),'missing')
    assert not result['assertions']['ah']
    assert 'CANONICAL_MAPPING_MISSING' in result['diagnostics']['codes']
    assert not any(n.get('semantic_status')=='UNLINKED' for n in session.store.ledger.data['nodes'].values())
