"""Concrete recovery/migration boundary checks, independent of gold answers."""
from copy import deepcopy
from dataclasses import replace

import pytest

from ah.core.journal import JournalIntegrityError
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.store_interface import MaterializationMarker, StoreOp, TerminalOutcome
from tools.formalizer_v7_extended_binding import Session, ATOM, OTHER
from tools.formalizer_v7_migration_binding import migration_action
from tools.formalizer_v7_test_support import journal_plan


@pytest.mark.parametrize('failure,old_live',[
    ('NONE',False),('BEFORE_STORE_COMMIT',True),('AFTER_STORE_BEFORE_TERMINAL',False),
    ('AFTER_SUCCESS_RETRACT_V2',False),('AMBIGUOUS_SENSE',True),('STALE_INPUT',True)])
def test_native_migration_atomic_retirement(tmp_path,failure,old_live):
    session=Session([],tmp_path/'journal')
    result=migration_action(session,'execute_migration',{
        'source':'O1','from_version':1,'to_version':2,'failure':failure,
        'mapping':'explicit_release_mapping','equivalence_supports':['EQ1']})
    assert result['migration']['old_supports_live'] is old_live
    assert result['migration']['old_records_rewritten'] is False
    assert result['migration']['alias_reasoner_enabled'] is False
    assert result['migration']['old_supports_resurrected'] is False
    if failure=='AFTER_STORE_BEFORE_TERMINAL':
        terminals=session.store._terminal_records()
        assert all('batch:'+key in terminals for key in session.store.ledger.data['decisions'])
    if failure=='AFTER_SUCCESS_RETRACT_V2':
        assert not session.store.ledger.f_visible()


@pytest.mark.parametrize('boundary',[
    'BEFORE_PLAN','AFTER_RESERVE','AFTER_ITEM_COMMIT_BEFORE_RECEIPT','AFTER_RECEIPT'])
def test_bulk_recovery_uses_reserved_versions_and_unique_receipts(tmp_path,boundary):
    session=Session([],tmp_path/'journal')
    result=migration_action(session,'recover_bulk_migration',{
        'boundary':boundary,'frozen_context_hash':'fixed-context','observations':['O2','O1'],
        'resource_snapshot':'reviewed-fixture','target_versions':{'O1':2,'O2':3}})['migration']
    assert result['item_order']==['O1','O2']
    assert result['reserved_target_versions']=={'O1':2,'O2':3}
    assert result['target_versions_reused'] is False
    assert result['item_receipts_unique'] is True
    assert result['provider_lock_observations']  # A real selection was probed.
    assert result['provider_holds_writer_lock'] is False
    assert set(result['target_commit_decisions'])=={'O1','O2'}
    assert all(D and D['outcome']=='APPLIED' and D['committed']
               for D in result['target_commit_decisions'].values())
    if boundary in {'AFTER_ITEM_COMMIT_BEFORE_RECEIPT','AFTER_RECEIPT'}:
        checkpoint=result['crash_checkpoint']
        assert checkpoint['observation_id']=='O1'
        assert checkpoint['target_version']==2
        assert checkpoint['marker_hash']==checkpoint['batch_hash']
        assert checkpoint['commit_decision']['committed']
        assert checkpoint['terminal']['outcome']=='APPLIED'
        assert checkpoint['receipt_durable'] is (boundary=='AFTER_RECEIPT')


def test_marker_replay_hash_integrity_and_exact_version_reconciliation(tmp_path):
    session=Session([],tmp_path/'journal')
    result=migration_action(session,'t6_with_marker',{
        'marker_hash':'H1','caller_hash':'H2','canonical_run':True})
    assert result['diagnostics']['codes']==['INTEGRITY_ERROR']
    assert result['journal']['new_fact_count']==0
    assert any(r['payload'].get('reason')=='COMMITTED_PAIR_HASH_MISMATCH'
               for r in session.store._journal.scan_unprocessed())
    session.store.reconcile_committed_pairs([session.batches['H1'][1].marker])
    with pytest.raises(JournalIntegrityError,match='declared committed pair has no marker'):
        session.store.reconcile_committed_pairs([MaterializationMarker('oracle:H1',2)])


def test_recovery_rejects_missing_marker_even_when_decision_survives(tmp_path):
    session=Session([ATOM],tmp_path/'journal');session.obs('source',ATOM)
    draft=session.store._draft();draft.store._state.formalizer_state['markers'].clear()
    # Simulate durable interference, not an ordinary partial transaction.
    session.store._write_unit(draft,tx_ref='fixture:corruption')
    with pytest.raises(JournalIntegrityError,match='commit decision marker mismatch'):
        session.store.recover_from_head()


def test_binding_premise_death_is_terminal_in_same_cascade(tmp_path):
    session=Session([ATOM,OTHER],tmp_path/'journal')
    _,antecedent_sid,_=session.obs('antecedent',ATOM)
    session.prepare('dependent',[OTHER]);ops,provisional,tag=session.batches['dependent']
    session.store.append_terminal('batch:dependent',TerminalOutcome.STALE_SUPERSEDED,'retagged typed fixture')
    binding=StoreOp('SET_IDENTITY_BINDING',{
        'binding_id':'B','target_ref':'fixture:M:'+digest('book'),
        'mention_ref':'mention:dependent','premise_support_refs':[antecedent_sid],
        'source_tag':tag},provisional.committed)
    adjusted=[]
    for op in ops:
        if op.op_type=='ADD_ROOT_SUPPORT':
            adjusted.append(binding)
            op=replace(op,payload={**op.payload,'binding_refs':['B']})
        adjusted.append(op)
    adjusted=tuple(adjusted)
    decision=journal_plan(session.store,adjusted,run_id=provisional.run_id,
        observation_id=tag[0],version=tag[1],batch_hash='dependent-bound',fragments=provisional.committed)
    session.store.commit_transaction(adjusted,decision.marker,decision)
    assert session.store.ledger.data['bindings']['B']['status']=='LIVE'
    dependent_sids=[sid for sid,s in session.store.ledger.data['supports'].items() if s.get('source_tag')==tag]
    session.store.retract_observation('oracle:antecedent',1,trigger_ref='premise-death')
    assert session.store.ledger.data['bindings']['B']['status']=='INVALID'
    assert all(session.store.ledger.data['supports'][sid]['status']=='SUPERSEDED' for sid in dependent_sids)
    session.store.recover_from_head()
    assert session.store.ledger.data['bindings']['B']['status']=='INVALID'


def test_reserved_target_migration_preserves_frozen_source_input(tmp_path):
    session=Session([],tmp_path/'journal')
    result=migration_action(session,'plan_migration',{'invalid_condition':'reused_target_version'})
    assert result['migration']['applied'] is False
    assert result['diagnostics']['codes']==['MIGRATION_REPLAY_MISMATCH']
    snapshots=[r['payload']['snapshot_data'] for r in session.store._journal.scan_unprocessed()
               if r['payload'].get('kind')=='run_bind' and r['payload']['observation_id']=='O1']
    assert len(snapshots)==2
    assert snapshots[0]['text']==snapshots[1]['text']=='Иван пришёл.'
    assert snapshots[1]['interpretation_version']==2
