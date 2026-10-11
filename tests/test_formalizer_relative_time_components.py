"""A relative relation is asserted; its unspecified event anchor is SOM-only."""
import pytest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.pipeline import MorphProvider
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release
from test_formalizer_components import Choices,frontend


@pytest.mark.parametrize('text,operator',[
    ('После завтрака принял Алека.','AFTER'),
    ('До совещания отдыхал.','BEFORE'),
])
def test_relative_anchor_has_no_root_or_absolute_time(tmp_path,text,operator):
    core=AHCore();release=with_components(test_release(core),relative_time=True)
    journal=JournalChannel(tmp_path/'journal');store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal)
    kwargs=dict(release=release,morph=MorphProvider(),run_id='relative',observation_id='O-relative')
    state,report=interpret_full(text,None,Choices([0]*8),store,binding,**kwargs)
    assert report.applied,(report,state.diagnostics)
    anchors=[uid for uid in store.ledger.data['nodes'] if uid.startswith('N:event-anchor:')]
    assert len(anchors)==1
    assert anchors[0] in store.ledger.s_accessible()
    assert not any(s['conclusion_ref']==anchors[0] for s in store.ledger.data['supports'].values())
    assert len(store.ledger.paths())==2
    assert not store.ledger.data['assertions']
    assert any(n.get('function_id')==operator for n in store.ledger.data['nodes'].values())
    _,repeat=interpret_full(text,None,Choices([0]*8),store,binding,**kwargs)
    assert repeat.batch_hash==report.batch_hash and len(store.ledger.paths())==2
    restored_core=AHCore();restored=AHStoreAdapter(restored_core.store,journal,restored_core)
    assert len(restored.ledger.paths())==2
    store.retract_observation(state.source_uid,1,trigger_ref='retract')
    assert anchors[0] not in store.ledger.s_accessible()


@pytest.mark.parametrize('text',['После раннего завтрака отдыхал.','После завтраком отдыхал.'])
def test_unsupported_anchor_is_not_simplified_or_recased(text):
    release=with_components(test_release(AHCore()),relative_time=True)
    st=frontend(text,MorphProvider(),Choices([0]*8),release)
    assert not st.frames or all(f.semantic['structural_unresolved'] for f in st.frames)


def test_known_nominal_anchor_is_not_replaced_by_an_open_template():
    release=with_components(test_release(AHCore(),[('BREAKFAST','завтрак','NOUN',[],'EVENT')]),relative_time=True)
    st=frontend('После завтрака отдыхал.',MorphProvider(),Choices([0]*8),release)
    assert not st.frames
