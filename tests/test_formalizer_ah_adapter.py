"""Typed AH operations, real digest/ownership, durable decision recovery."""
from dataclasses import replace
import pytest
from ah.core.journal import JournalChannel,JournalIntegrityError
from ah.core.store import AHStore
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.store_interface import StoreOp,AssertionStatus
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import journal_plan

@pytest.fixture
def store(tmp_path):return AHStoreAdapter(AHStore(),JournalChannel(tmp_path/'journal.log'))

def plan():
    tag=['obs1',2];prop={'predicate':'test-predicate','actants':{'SUBJECT':'M'}};ck=digest(prop)
    specs=[('ENSURE_ENTITY',{'uid':'M','name':'Иван'}),('ENSURE_TEMPLATE',{'uid':'T','predicate_form':'test-predicate','roles':['SUBJECT'],'semantic_status':'UNLINKED'}),('ENSURE_NODE',{'uid':'N','template_ref':'T','actants':{'SUBJECT':'M'},'proposition':prop,'content_key':ck,'temporal_mode':'STATE'}),('ADD_ROOT_SUPPORT',{'record_id':'S','conclusion_ref':'N','kind':'ROOT','ground_type':'O','source_tag':tag}),('DECLARE_FRAGMENT',{'fragment_id':'F1','node_ref':'N','source_tag':tag,'proposition':prop,'content_key':ck,'polarity':True})]
    return tuple(StoreOp(k,v,('F1',)) for k,v in specs)

def reopen(store):return AHStoreAdapter(AHStore(),JournalChannel(store._journal.path))

def test_commit_durable_idempotent(store):
    ops=plan();d=journal_plan(store,ops)
    assert store.commit_transaction(ops,d.marker,d).outcome.value=='APPLIED'
    restored=reopen(store)
    assert restored.commit_transaction(ops,d.marker,d).idempotent_noop
    assert len(restored.ledger.data['supports'])==1 and 'N' in restored.ledger.f_visible()

def test_crash_after_atomic_d_before_terminal(store,monkeypatch):
    ops=plan();d=journal_plan(store,ops)
    def crash(_):raise RuntimeError('crash after D')
    monkeypatch.setattr(store,'_finish_batch',crash)
    with pytest.raises(RuntimeError,match='crash'):store.commit_transaction(ops,d.marker,d)
    restored=reopen(store)
    assert 'h1' in restored.ledger.data['decisions']
    assert not restored.pending_batches()
    assert len(restored.ledger.data['supports'])==1
    assert len([r for r in restored._journal.scan_unprocessed(0) if r['payload'].get('kind')=='terminal' or r['payload'].get('terminal')])==1

def test_terminal_not_double_restored(store):
    ops=plan();d=journal_plan(store,ops);store.commit_transaction(ops,d.marker,d)
    restored=reopen(store);head=restored.read_global_head()
    assert not restored.recover_from_head().recovered and restored.read_global_head()==head

def test_retraction_durable(store):
    ops=plan();d=journal_plan(store,ops);store.commit_transaction(ops,d.marker,d)
    store.retract_observation('obs1',2,trigger_ref='explicit:test')
    restored=reopen(store)
    assert restored.ledger.data['supports']['S']['status']=='SUPERSEDED'
    assert restored.ledger.query_proposition('N')['answer']=='UNKNOWN'

def test_unknown_retraction_integrity_error_without_mutation(store):
    before=digest(store._codec.export(store._core));head=store.read_global_head()
    with pytest.raises(JournalIntegrityError,match='INTEGRITY_ERROR: unknown retraction record'):
        store.retract('ghost',AssertionStatus.SUPERSEDED)
    assert digest(store._codec.export(store._core))==before
    assert store.read_global_head()==head

def test_wrong_digest_refused(store):
    ops=plan();d=journal_plan(store,ops)
    with pytest.raises(JournalIntegrityError):store.commit_transaction(ops,d.marker,replace(d,ops_digest='wrong'))
