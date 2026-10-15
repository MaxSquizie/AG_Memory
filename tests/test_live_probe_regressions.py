"""Failures observed in the 2026-10-15 GUI run; no live-model quality claim."""
from copy import deepcopy

import pytest

from test_structural_relation_tasks import run,relation,atom


@pytest.mark.parametrize('text,predicate',[
    ('Иван вошёл.','ENTER'),('Иван пришёл.','ARRIVE'),('Иван работает.','WORK'),
])
def test_identical_producers_need_no_model_preference(tmp_path,monkeypatch,text,predicate):
    result,script=run(tmp_path,monkeypatch,text,relation('LEXICAL'),default='?')
    assert result['assertions']['ah']==[atom(predicate,'ivan')]
    assert [slot for slot,_ in script.calls]==['structural_relation']
    trace=result['runtime']['ir']['syntax_trace']
    assert any(r.get('kind')=='COMPOSITION_EQUIVALENT_SOURCES' for r in trace)


def test_clock_colon_is_owned_by_temporal_syntax(tmp_path,monkeypatch):
    from tools.formalizer_v7_native_binding import ChatBackend,execute_native
    from tools.formalizer_v7_extended_binding import Session
    from test_structural_relation_tasks import Script
    script=Script(relation('LEXICAL'),default='?')
    monkeypatch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:script.generate(prompt,**kw))
    text='В 09:00 иван вошёл.'
    payload={'raw_input':{'text':text,'source_id':'clock-regression','revision':1,
        'range':[0,len(text)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE',
        'source_timestamp':'2026-10-09T12:00:00+00:00'}}
    result=execute_native(Session([payload],tmp_path/'j'),payload,
        {'provider':'lmstudio','model':'recorded-lexical-choice','structure_mode':'region_probes'})
    assert not script.steps and not script.errors
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[atom('ENTER','ivan')]
    assert result['time_assertions']['semantics']==['POINT']


@pytest.mark.parametrize('difference',['role','morphology','scope','implicit','sense'])
def test_distinct_interpretations_are_not_coalesced(tmp_path,monkeypatch,difference):
    import ah.formalizer.composition_source_union as union
    from ah.formalizer.composition_equivalence import coalesce,describe
    original=union.merge;checked=[]
    def inspect(state,release,selector,region,tokens,cfg,grammar,components,before):
        if grammar and components:
            left,right=deepcopy(grammar[0]),deepcopy(components[0])
            first=coalesce(state,release,region,[(left,[left],''),(right,[right],'')])
            assert len(first[0])==1
            if difference=='role':right.semantic['proposed_roles'][right.argument_token_refs[0]]='OBJECT'
            if difference=='morphology':right.semantic['morph_bindings'][right.predicate_token_ref]['tense']='present'
            if difference=='scope':right.semantic['operator_forest']=[{'operator':'NOT','operands':[{'frame_ref':right.frame_id}]}]
            if difference=='implicit':right.semantic['implicit_arguments']={'OBJECT':{'gap_id':'another'}}
            if difference=='sense':right.semantic['candidate_specs']={'other':{'sense_id':'OTHER'}}
            bundles,duplicates=coalesce(state,release,region,[(left,[left],''),(right,[right],'')])
            assert len(bundles)==2 and not duplicates
            assert describe(state,left,[left])!=describe(state,right,[right])
            checked.append(True)
        return original(state,release,selector,region,tokens,cfg,grammar,components,before)
    monkeypatch.setattr(union,'merge',inspect)
    run(tmp_path,monkeypatch,'Иван пришёл.',relation('LEXICAL'),default='?')
    assert checked


def test_unowned_colon_still_blocks_lexical_reading(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Иван: пришёл.',relation('LEXICAL')+[
        ('structural_revision','DEFER')],default='?')
    assert not result['assertions']['ah']
    assert 'COMPONENT_SCOPE_UNRESOLVED' in result['diagnostics']['codes']


def test_equivalent_source_trace_is_readable():
    from test_formalization_readable import sample,visible
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    data=sample();data['state']['syntax_trace']=[{'kind':'COMPOSITION_EQUIVALENT_SOURCES',
        'source_range':[0,26],'predicate_ref':'read','roles':{'student':'SUBJECT'}}]
    inspection=Inspection(data);reader=ReadableInspection(inspection)
    rendered=visible(reader.explain(inspection.by_ref['trace:0']))
    assert 'Выбор источника не требует вопроса модели' in rendered
    assert 'читает' in rendered and 'студент' in rendered
    assert 'Выбор источника не требует вопроса модели' in reader.report([])


@pytest.mark.parametrize('text,predicate,person,role,entity',[
    ('Иван сидит на стуле.','SIT_STATE','ivan','LOCATION','chair'),
    ('Пётр сидит в комнате.','SIT_STATE','petr','LOCATION',None),
    ('Иван приехал в Москву.','ARRIVE_CITY','ivan','DESTINATION','moscow'),
    ('Иван уехал из Москвы.','DEPART_CITY','ivan','SOURCE','moscow'),
])
def test_fixture_government_makes_prepositional_roles_reachable(tmp_path,monkeypatch,text,predicate,person,role,entity):
    result,script=run(tmp_path,monkeypatch,text,relation('LEXICAL'))
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0]['predicate']==predicate
    assert role in facts[0]['roles']
    if entity:assert facts[0]['roles'][role]=={'entity':entity}
    assert not any(slot in {'nominal_attachment','modifier_scope','source_assertion'} for slot,_ in script.calls)
    assert not result['diagnostics']['codes']


def test_optional_location_is_not_invented(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Иван сидит.',relation('LEXICAL'),default='?')
    assert result['assertions']['ah']==[{'predicate':'SIT_STATE','roles':{'THEME':{'entity':'ivan'}}}]


def test_temporal_words_cannot_become_quality_predicates(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Весь вчерашний день иван — врач.',
        relation('LEXICAL'))
    # The nominal predicate is reachable; the lower-case name is unresolved.
    # Neither outcome licenses a false OPEN:весь fact.
    assert result['assertions']['ah']==[]
    frames=result['runtime']['ir']['frames']
    assert not any(f['anchor_span'].lower() in {'весь','вчерашний'} and
                   not f['semantic'].get('structural_unresolved') for f in frames)
    assert any(r.get('kind')=='TEMPORAL_PREDICATE_EXCLUDED' for r in result['runtime']['ir']['syntax_trace'])


@pytest.mark.parametrize('text,object_word',[('Иван читает книгу.','книгу'),('Пётр написал письмо.','письмо')])
def test_completed_dependency_provenance_is_not_a_linguistic_choice(tmp_path,monkeypatch,text,object_word):
    result,script=run(tmp_path,monkeypatch,text,relation('LEXICAL')+[
        ('nominal_dependency','Direct role OBJECT')],default='?')
    assert len(result['assertions']['ah'])==1
    assert not any(slot=='child_slot' for slot,_ in script.calls)
    rows=[r for r in result['runtime']['ir']['syntax_trace'] if r.get('kind')=='COMPOSITION_EQUIVALENT_SOURCES']
    assert any(q['kind']=='FIXED_DEPENDENCY' for r in rows for s in r['sources'] for q in s['component_questions'])


@pytest.mark.parametrize('kind,expected',[
    ('STRUCTURAL_REVISION_STALLED','Повторены те же локальные решения'),
    ('TEMPORAL_PREDICATE_EXCLUDED','распознанное временное выражение'),
])
def test_new_failure_paths_have_readable_gui_explanations(kind,expected):
    from test_formalization_readable import sample,visible
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    data=sample();data['state']['syntax_trace']=[{'kind':kind,'source_range':[0,26],'predicate_ref':'read'}]
    inspection=Inspection(data);reader=ReadableInspection(inspection)
    assert expected in visible(reader.explain(inspection.by_ref['trace:0']))
    assert expected in reader.report([])
