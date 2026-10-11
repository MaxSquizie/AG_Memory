"""Released valency composition; no diary lexemes in the algorithm."""
import pytest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.native_frontend import _bindings
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release, role
from test_formalizer_components import frontend, Choices


@pytest.fixture(scope='module')
def morph(): return MorphProvider()


def released(core, lemma, prep, case, role_id):
    oblique={**role(role_id,(case,)), 'allowed_preps':[prep]}
    return with_components(test_release(core,[('ACTION',lemma,'VERB',
        [role('SUBJECT'),oblique],'EVENT')]))


@pytest.mark.parametrize('text,lemma,prep,case,slot',[
    ('Покатались на шлюпках.','покататься','на','loc','TOOL'),
    ('Говорил с врачом.','говорить','с','abl','RECIPIENT'),
    ('Вернулся из города.','вернуться','из','gen','SOURCE'),
    ('Стоял у окна.','стоять','у','gen','LOCATION'),
])
def test_released_prepositional_argument_commits_and_replays(tmp_path,morph,text,lemma,prep,case,slot):
    core=AHCore(); release=released(core,lemma,prep,case,slot)
    journal=JournalChannel(tmp_path/'journal');store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal)
    args=dict(release=release,morph=morph,run_id='pp-run',
        raw_input={'source_id':'test-pp','range':[0,len(text)]})
    st,receipt=interpret_full(text,None,Choices([0]*8),store,binding,**args)
    assert receipt.applied, (receipt,st.diagnostics)
    fs=[f for f in st.frames if not f.semantic['structural_unresolved']]
    assert len(fs)==1
    f=fs[0]; questions=[q for q in f.semantic['component_questions'] if q['kind']=='RELATION_TO_EVENT']
    assert len(questions)==1 and questions[0]['status']=='BOUND' and questions[0]['role']==slot
    assert questions[0]['children'][0]['kind']=='ARGUMENT_CONTENT'
    assert not f.semantic['uncovered_token_refs']
    paths=store.ledger.paths(); assert len(paths)==1
    target=store._store.get_element_any_domain(store.ledger.data['supports'][next(iter(paths))]['conclusion_ref'])
    assert slot in target.actants
    # Preposition is relation evidence, not part of the entity's name.
    entity=store._store.get_element_any_domain(target.actants[slot].uid)
    assert not entity.properties['name'].value.casefold().startswith(prep+' ')
    # Native provider-free scripted replay keeps the same operation digest.
    again,second=interpret_full(text,None,Choices([0]*8),store,binding,**args)
    assert second.terminal=='APPLIED' and second.batch_hash==receipt.batch_hash
    assert not second.applied and len(store.ledger.paths())==1
    restored_core=AHCore(); restored=AHStoreAdapter(restored_core.store,journal,restored_core)
    assert len(restored.ledger.paths())==1
    store.retract_observation(st.source_uid,1,trigger_ref='test-pp-retraction')
    assert not store.ledger.paths()


def test_unreleased_pp_has_nested_question_without_invented_semantics(morph):
    st=frontend('После завтрака принял Алека.',morph)
    assert st.frames
    for f in st.frames:
        qs=[q for q in f.semantic['component_questions'] if q['kind']=='RELATION_TO_EVENT']
        assert len(qs)==1 and qs[0]['status']=='UNRESOLVED'
        assert qs[0]['role'] is None
        assert f.semantic['structural_unresolved']
        assert not f.semantic['preposition_bindings']
    assert not st.observation['implicit_bindings']


def test_t3_cannot_reinterpret_pp_as_bare_case_role(morph):
    release=released(AHCore(),'говорить','с','abl','RECIPIENT')
    st=frontend('Говорил с врачом.',morph,Choices([0]*8),release)
    f=next(f for f in st.frames if not f.semantic['structural_unresolved'])
    wrong={'roles':[role('SUBJECT'),role('RECIPIENT',('abl',))]}
    assert _bindings(f,{e.token_id:e for e in st.evidence},wrong,('SUBJECT',))==[]


@pytest.mark.parametrize('text',['Говорил без врача.','Говорил врачом.','Говорил с врача.'])
def test_wrong_preposition_or_case_does_not_commit(morph,text):
    st=frontend(text,morph,Choices([0]*8),released(AHCore(),'говорить','с','abl','RECIPIENT'))
    assert st.frames
    assert all(f.semantic['structural_unresolved'] for f in st.frames)
    assert all('RECIPIENT' in f.semantic['missing_required_roles'] for f in st.frames)


def test_adjective_in_pp_keeps_mention_separate_from_preposition(morph):
    st=frontend('Стоял у большого окна.',morph,Choices([0]*8),
        released(AHCore(),'стоять','у','gen','LOCATION'))
    f=next(f for f in st.frames if not f.semantic['structural_unresolved'])
    head=next(iter(f.semantic['preposition_bindings']))
    assert f.semantic['lexical_units'][head]['surface']=='большого окна'
    assert len(f.semantic['lexical_units'][head]['anchor_refs'])==2


def test_ambiguous_preposition_requires_positive_structural_probe(morph):
    selector=Choices()
    st=frontend('Говорил с врачом.',morph,selector,
        released(AHCore(),'говорить','с','abl','RECIPIENT'))
    assert len(selector.prompts)==1
    assert st.frames and all(f.semantic['structural_unresolved'] for f in st.frames)
    assert not st.observation['implicit_bindings']
