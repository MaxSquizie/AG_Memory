"""Historical context validation changes neither WAL nor attention."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from ah.formalizer.attention_context import AttentionContextReader,freeze_attention_base,attention_snapshot,ContextReadError
from ah.formalizer.pipeline import t0
from ah.model import Domain
from test_region_attention import engine,read_request
from tools.formalizer_v7_test_support import native_fixture


@pytest.fixture
def context(tmp_path):
    store,_,release=native_fixture(tmp_path/'journal')
    live=engine(store._core)
    parent=AttentionContextReader(store,release,live,'receipt-test',freeze_attention_base(store,live))
    reader=parent.fork('left');state=t0('А Б.');state.observation={}
    request=read_request(state);reader.read(state,request)
    return store,parent,reader,state,request,live


def snapshot(store,reader,live):
    return (store._journal.path.read_bytes(),store._journal._head,reader.ordinal,
            deepcopy(reader.read_token_refs),attention_snapshot(reader.engine),attention_snapshot(live))


def test_current_receipt_validation_is_read_only_even_after_attention_moves(context):
    store,parent,reader,state,_,live=context
    live.tick(include_pacemaker=False)
    before=snapshot(store,reader,live)
    assert reader.validate_context_receipts(state.context_reads)['status']=='CURRENT'
    assert snapshot(store,reader,live)==before
    assert parent.fork('right').validate_context_receipts(state.context_reads)['status']=='STALE'


@pytest.mark.parametrize('field',['rows','proof_results','result_hash','run','ordinal','request'])
def test_delivered_receipt_mutation_is_rejected(context,field):
    _,_,reader,state,_,_=context
    receipt=deepcopy(state.context_reads[0])
    if field=='rows':receipt['rows'].append({'invented':True})
    elif field=='proof_results':receipt['proof_results'].append({'status':'PROVED'})
    elif field=='result_hash':receipt['result_hash']='changed'
    elif field=='run':receipt['request']['run_id']='other'
    elif field=='ordinal':receipt['request']['ordinal']+=1
    else:receipt['request']['decision_ref']='another-question'
    assert reader.validate_context_receipts([receipt])['status']!='CURRENT'


def test_canonical_and_release_changes_retire_receipt(context):
    store,_,reader,state,_,_=context
    original=reader.release;reader.release=SimpleNamespace(sha256='changed')
    assert reader.validate_context_receipts(state.context_reads)['reason']=='CONTEXT_RELEASE_CHANGED'
    reader.release=original
    store._core.add_entity(Domain.C)
    assert reader.validate_context_receipts(state.context_reads)['reason']=='CONTEXT_SNAPSHOT_STALE'


def test_torn_tail_is_not_repaired_by_validation(context):
    store,_,reader,state,_,live=context
    with store._journal.path.open('ab') as f:f.write(b'{"torn":')
    before=snapshot(store,reader,live)
    assert reader.validate_context_receipts(state.context_reads)=={
        'status':'UNAVAILABLE','reason':'CONTEXT_JOURNAL_UNAVAILABLE'}
    assert snapshot(store,reader,live)==before


def test_duplicate_wal_receipt_is_not_selected_arbitrarily(context):
    store,_,reader,state,_,live=context
    row=next(r for r in store._journal.verified_snapshot()['records'] if r['payload'].get('kind')=='CONTEXT_READ')
    store._journal.append(row['channel'],row['payload'],run_id=row['run_id'])
    before=snapshot(store,reader,live)
    assert reader.validate_context_receipts(state.context_reads)['reason']=='CONTEXT_RECEIPT_NOT_UNIQUE'
    assert snapshot(store,reader,live)==before


def test_replay_after_memory_change_does_not_restore_old_attention(context):
    store,parent,reader,state,request,live=context
    replay=parent.fork('left');fresh=t0(state.text);fresh.observation={}
    store._core.add_entity(Domain.C)
    before=snapshot(store,replay,live)
    with pytest.raises(ContextReadError,match='CONTEXT_SNAPSHOT_STALE'):replay.read(fresh,request)
    after=snapshot(store,replay,live)
    assert before[0:2]==after[0:2] and before[3:]==after[3:]
    assert not fresh.context_reads


def test_parent_same_goal_cannot_supply_branch_receipt(context):
    from ah.formalizer.context_receipts import associate
    store,parent,_,_,_,_=context
    state=t0('А Б.');state.observation={}
    request={**read_request(state),'decision_ref':'composition-context:shared-goal'}
    parent.read(state,request)
    child=parent.fork('new-branch');inherited=deepcopy(state)
    child.read(inherited,request)
    assert len({r['request']['run_id'] for r in inherited.context_reads})==2
    selected,missing=associate(child,['goal:shared-goal'],inherited.context_reads)
    assert not missing and len(selected)==1
    assert selected[0]['request']['run_id']==child.run_id
    assert child.validate_context_receipts(selected)['status']=='CURRENT'
    assert associate(child,['goal:shared-goal'],state.context_reads)[1]==['goal:shared-goal']


def test_unseen_canonical_commit_requires_refresh_without_performing_it(context):
    store,_,reader,state,_,live=context
    store._journal.append('canonical',{'kind':'canonical_unit'},run_id='other-writer')
    before=snapshot(store,reader,live)
    assert reader.validate_context_receipts(state.context_reads)['reason']=='CANONICAL_REFRESH_REQUIRED'
    assert snapshot(store,reader,live)==before


def test_full_result_hash_is_checked_beyond_delivery_projection(context):
    import hashlib
    from ah.core.journal import canonical_json
    store,_,reader,state,_,live=context
    records=store._journal.verified_snapshot()['records']
    row=next(r for r in records if r['payload'].get('kind')=='CONTEXT_READ')
    row['payload']['result']['attention_after']['tick']+=1
    # Frame checksum is valid: only the nested full-result receipt is stale.
    body={k:v for k,v in row.items() if k!='checksum'}
    row['checksum']=hashlib.sha256(canonical_json(body).encode()).hexdigest()
    store._journal.path.write_bytes(('\n'.join(canonical_json(r) for r in records)+'\n').encode())
    before=snapshot(store,reader,live)
    assert reader.validate_context_receipts(state.context_reads)['reason']=='CONTEXT_RECEIPT_CHANGED'
    assert snapshot(store,reader,live)==before
