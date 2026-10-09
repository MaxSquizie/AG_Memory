"""Native T0..T6 contracts with an actual signed isolated release and WAL."""
import pytest
from ah.core.journal import JournalChannel
from ah.core.store import AHStore
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.selection_protocol import load_decision_schema
from ah.formalizer.v7_pipeline import interpret_full,run_from_state
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import native_fixture,NativeSelector,FixtureMorph

TEXT='У Ивана есть книга.'
@pytest.fixture
def native(tmp_path):return native_fixture(tmp_path/'journal.log')

def invoke(native,selector=None,**kwargs):
    store,binding,release=native
    return interpret_full(TEXT,load_decision_schema(),selector or NativeSelector(),store,binding,release=release,morph=FixtureMorph(),raw_input={'source_id':'pipeline-test','revision':1},run_id='r1',**kwargs)

def test_native_fact_commits(native):
    _,rep=invoke(native)
    assert rep.t5_eligibility=='OK' and rep.applied and rep.terminal=='APPLIED'
    assert rep.committed_fragments and native[0].ledger.f_visible()

def test_unresolved_is_resolution_only(native):
    _,rep=invoke(native,NativeSelector(unresolved=True))
    assert rep.terminal=='RESOLUTION_ONLY' and not rep.applied
    assert not native[0].ledger.f_visible()
    assert native[0]._journal.scan_unprocessed(0,'resolution_log')

def test_synthetic_state_without_observation_cannot_invent_o(native):
    state,_=invoke(native,NativeSelector(unresolved=True))
    for d in state.decisions.values():
        if d.candidates:
            d.selected=d.candidates[:1];d.outcome='RESOLVED'
    state.observation={};state.source_uid='synthetic'
    rep=run_from_state(state,native[0],native[1],release=native[2],run_id='synthetic',version=1)
    assert not rep.applied and not rep.committed_fragments
    assert any('COND_5' in d for d in rep.diagnostics)

def test_foreign_owner_blocks(native):
    from ah.formalizer.v7_pipeline import _observation
    oid=_observation(TEXT,version=1,raw_input={'source_id':'pipeline-test','revision':1})['observation_id']
    assert native[1].acquire('foreign',oid,1)
    _,rep=invoke(native)
    assert not rep.binding_ok and rep.t5_eligibility=='INTEGRITY_ERROR' and not rep.applied

def test_restart_idempotence(native):
    _,first=invoke(native)
    journal=JournalChannel(native[0]._journal.path)
    restored=AHStoreAdapter(AHStore(),journal)
    _,again=invoke((restored,InterpretationRunBinding(journal),native[2]))
    assert first.applied and not again.applied and first.batch_hash==again.batch_hash
    assert len(restored.ledger.data['supports'])==1

def test_missing_release_still_refused(native):
    _,rep=interpret_full(TEXT,load_decision_schema(),NativeSelector(),native[0],native[1],raw_input={'source_id':'missing'},run_id='missing')
    assert rep.t5_eligibility=='RESOURCE_MISSING' and not rep.applied

def test_changed_context_same_pair_rejected(native):
    invoke(native)
    with pytest.raises(RuntimeError,match='snapshot'):
        invoke(native,context_facts=('changed context',))
