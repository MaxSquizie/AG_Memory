"""Current typed plan boundary: no IR-to-identity side channel or implicit writes.

Legacy ADD_SCOPE/ADD_GROUP helpers have been replaced by native_plan and the
canonical ledger. Graph durability and ownership are exercised on that route.
"""
from ah.formalizer.commit_stage import commit
from ah.formalizer.pipeline import t0
from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.native_plan import build_plan
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.selection_protocol import load_decision_schema
from tools.formalizer_v7_test_support import native_fixture,NativeSelector,FixtureMorph


def test_commit_without_an_admitted_plan_is_resolution_only():
    store=MemoryStore();state=t0('Unresolved source')
    result=commit(state,store,run_id='resolution-only')
    assert not result.applied and result.n_ops==0
    assert result.terminal.value=='RESOLUTION_ONLY'


def test_native_plan_preserves_bindings_and_blocked_scope(tmp_path):
    store,binding,release=native_fixture(tmp_path/'journal.log')
    state,report=interpret_full('У Ивана есть книга.',load_decision_schema(),NativeSelector(),store,binding,
        release=release,morph=FixtureMorph(),raw_input={'source_id':'typed-plan','revision':1},run_id='typed')
    assert report.applied and store.ledger.f_visible()
    operations,fragments,_,_=build_plan(state,release,store)
    assert fragments and any(o.op_type=='ENSURE_NODE' for o in operations)
    assert any(o.op_type=='SET_IDENTITY_BINDING' for o in operations)
    before=store.ledger.f_visible()
    for frame in state.frames:frame.semantic['structural_unresolved']=True
    operations,fragments,_,_=build_plan(state,release,store)
    assert not fragments and not any(o.op_type=='ADD_ROOT_SUPPORT' for o in operations)
    assert store.ledger.f_visible()==before


def test_unresolved_reference_cannot_materialize_an_identity(tmp_path):
    store,binding,release=native_fixture(tmp_path/'journal.log')
    state,report=interpret_full('У Ивана есть книга.',load_decision_schema(),NativeSelector(unresolved=True),store,binding,
        release=release,morph=FixtureMorph(),raw_input={'source_id':'unresolved-plan','revision':1},run_id='unresolved')
    assert not report.applied and not store.ledger.f_visible() and not store.ledger.data['bindings']
    operations,fragments,_,_=build_plan(state,release,store)
    assert not fragments and not any(o.op_type=='SET_IDENTITY_BINDING' for o in operations)
