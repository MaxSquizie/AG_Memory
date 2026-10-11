"""An enclosing coordination must never leak a conjunct before selection."""
from ah.core import AHCore
import pytest
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.pipeline import MorphProvider
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release
from test_formalizer_components import Choices,frontend


def test_coordination_commits_and_group_identity_is_a_separate_probe(tmp_path):
    core=AHCore();release=with_components(test_release(core))
    journal=JournalChannel(tmp_path/'journal');store=AHStoreAdapter(core.store,journal,core)
    # Coordination then first unidentified group then continuation of that group.
    selector=Choices([0,0,lambda cid:cid.startswith('gap:')])
    st,report=interpret_full('Покатались и купались.',None,selector,store,InterpretationRunBinding(journal),
        release=release,morph=MorphProvider(),run_id='coord')
    assert report.applied,report
    assert len(report.committed_fragments)==1
    assert len(store.ledger.paths())==3  # AND root and two derived occurrences
    refs=[v['entity_ref'] for v in st.observation['implicit_bindings'].values()]
    assert len(refs)==2 and refs[0]==refs[1]
    group=store._store.get_element_any_domain(refs[0])
    assert group.meta['implicit_participant']['membership_status']=='UNKNOWN'
    assert all(f.semantic.get('operator_forest') for f in st.frames)
    recovered_core=AHCore();recovered=AHStoreAdapter(recovered_core.store,journal,recovered_core)
    assert len(recovered.ledger.paths())==3
    store.retract_observation(st.source_uid,1,trigger_ref='withdraw-conjunction')
    assert not store.ledger.paths()


def test_rejected_coordination_has_no_independently_assertible_child():
    st=frontend('Покатались и купались.',MorphProvider(),Choices())
    assert len(st.frames)==2
    assert all(f.semantic['structural_unresolved'] and f.semantic['coordination_owner'] for f in st.frames)
    assert not st.observation['implicit_bindings']


def test_partial_conjunct_blocks_the_whole_composition():
    st=frontend('Покатались на шлюпках и купались.',MorphProvider(),Choices([0]*8))
    assert len(st.frames)==2
    assert all(f.semantic['structural_unresolved'] for f in st.frames)
    assert not st.observation['implicit_bindings']


@pytest.mark.parametrize('text',['Не купались и отдыхали.','«Купались и отдыхали.»','Купались и отдыхали?'])
def test_scoped_coordination_does_not_become_asserted(text):
    st=frontend(text,MorphProvider(),Choices([0]*8))
    assert not st.frames or all(f.semantic['structural_unresolved'] for f in st.frames)
    assert not st.observation['implicit_bindings']
