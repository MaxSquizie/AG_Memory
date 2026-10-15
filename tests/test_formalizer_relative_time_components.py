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
    nodes=store.ledger.data['nodes']
    relation,=[n for n in nodes.values() if n.get('function_id')==operator]
    main,anchor=relation['operands']
    evidence={e.token_id:e.span for e in state.evidence}
    assert evidence[nodes[anchor]['source_ref']] in {'завтрака','совещания'}
    assert nodes[anchor]['temporal_mode']=='UNKNOWN'
    assert {s['conclusion_ref'] for s in store.ledger.data['supports'].values()}=={relation['uid'],main}
    assert anchor in store.ledger.s_accessible()
    assert not any(s['conclusion_ref']==anchor for s in store.ledger.data['supports'].values())
    assert len(store.ledger.paths())==2
    assert not store.ledger.data['assertions']
    _,repeat=interpret_full(text,None,Choices([0]*8),store,binding,**kwargs)
    assert repeat.batch_hash==report.batch_hash and len(store.ledger.paths())==2
    restored_core=AHCore();restored=AHStoreAdapter(restored_core.store,journal,restored_core)
    assert len(restored.ledger.paths())==2
    store.retract_observation(state.source_uid,1,trigger_ref='retract')
    assert anchor not in store.ledger.s_accessible()


@pytest.mark.parametrize('text',['После раннего завтрака отдыхал.','После завтраком отдыхал.'])
def test_unsupported_anchor_is_not_simplified_or_recased(text):
    release=with_components(test_release(AHCore()),relative_time=True)
    st=frontend(text,MorphProvider(),Choices([0]*8),release)
    assert not st.frames or all(f.semantic['structural_unresolved'] for f in st.frames)


def test_known_nominal_anchor_is_not_replaced_by_an_open_template():
    release=with_components(test_release(AHCore(),[('BREAKFAST','завтрак','NOUN',[],'EVENT')]),relative_time=True)
    st=frontend('После завтрака отдыхал.',MorphProvider(),Choices([0]*8),release)
    assert any(d.code=='COMPOSITION_SLOT_UNCLOSED' for d in st.diagnostics)
    assert all(f.semantic['structural_unresolved'] for f in st.frames)
    assert not st.observation['implicit_bindings']
    assert all(f.anchor_span!='завтрака' for f in st.frames)
