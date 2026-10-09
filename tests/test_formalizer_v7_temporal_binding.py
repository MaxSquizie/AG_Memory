"""Verify actual temporal binder records and retraction boundaries."""
from itertools import product
import pytest
from tools.formalizer_v7_extended_binding import Session, OR, NOT
from tools.formalizer_v7_temporal_binding import (
    ATOM, OTHER, ARRIVE, TEMPORAL_FIXTURES, temporal_action,
)
from ah.formalizer.temporal_constraints import validate_order_constraints, derive_declared_region
from ah.formalizer.temporal_license import cont, point
from ah.formalizer.inference_engine import InferenceRule


def session(tmp_path, *payloads):
    return Session([*payloads, *TEMPORAL_FIXTURES], tmp_path / 'journal.log')


@pytest.mark.parametrize('variant,scope', list(product(
    ['OBSERVATION_ROOT', 'OBSERVATION_AND_DERIVED', 'GOAL_RUN_DERIVED'],
    ['OBSERVATION', 'ASSERTION', 'BINDING', 'PREMISE'])))
def test_temporal_retraction_respects_source_and_path(tmp_path, variant, scope):
    s = session(tmp_path)
    result = temporal_action(s, 'retract_time_path', {
        'source_support_variant': variant, 'trigger_scope': scope,
        'assertion_id': 'A', 'another_live_path': False,
    })
    retracted = scope == 'ASSERTION' or scope == 'OBSERVATION' and variant != 'GOAL_RUN_DERIVED'
    assert result['time_assertions']['A']['status'] == ('RETRACTED' if retracted else 'LIVE')
    assert not result['time_assertions']['A']['effective']
    assert result['supports']['original_alive'] == (scope == 'ASSERTION')
    assert result['journal']['time_retraction_count'] == int(retracted)
    s.store.ledger.validate_audit()


@pytest.mark.parametrize('rule,shared,same_tag', list(product(
    ['OR_ELIMINATION', 'FORALL_INST'], [False, True], [False, True])))
def test_same_source_is_not_shared_existential_witness(tmp_path, rule, shared, same_tag):
    s = session(tmp_path)
    result = temporal_action(s, 'correlated_inference', {
        'rule': rule, 'same_source_tag': same_tag,
        'witnesses': [{'kind': 'INTERVAL', 'bounds': [0, 3], 'semantics': 'EXISTENTIAL'}] * 2,
        'shared_witness_ref': 'W_AND' if shared else None,
        'shared_witness_proof': {'root_support': 'S_AND', 'assertion_refs': ['A1', 'A2']} if shared else None,
    })
    assert result['license']['valid'] == shared
    assert result['derived']['support_count'] == int(shared)
    assert result['derived']['witness_ref'] == ('W_AND' if shared else None)
    assert not result['derived']['is_continuous']
    s.store.ledger.validate_audit()


@pytest.mark.parametrize('ground,independent', [('R', True), ('W', False), ('C', False)])
def test_shared_factual_sources_affect_metric_not_path_retraction(tmp_path, ground, independent):
    s = session(tmp_path)
    result = temporal_action(s, 'proof_independence', {
        'observation_sources': ['O1', 'O2'], 'shared_ground': ground, 'supports': ['s1', 's2'],
    })
    assert result['proof']['independent'] == independent
    assert result['proof']['retract_O1_keeps_s2']
    assert result['store']['fact_count'] == 1


@pytest.mark.parametrize('rule', ['AND_ELIMINATION', 'OR_ELIMINATION', 'FORALL_INST'])
def test_registered_derivation_can_conclude_not_root(tmp_path, rule):
    conclusion = {'operator': 'NOT', 'operands': [ARRIVE]}
    s = session(tmp_path, conclusion)
    result = temporal_action(s, 'derive_operator_conclusion', {
        'rule_id': rule, 'conclusion': conclusion, 'premises_proven': True, 'same_time_license': True,
    })
    assert result['derived']['conclusion_type'] == 'G'
    assert result['derived']['support_count'] == 1
    assert result['derived']['root_support_count'] == 0
    assert result['operands']['independent_truth_count'] == 0


def test_commit_time_conjunction_keeps_three_correlated_assertions(tmp_path):
    s = session(tmp_path)
    temporal_action(s, 'commit_dated_conjunction', {
        'root': {'operator': 'AND', 'operands': [ATOM, OTHER]}, 'source': 'O_and',
        'window': {'kind': 'INTERVAL', 'bounds': [0, 3], 'semantics': 'EXISTENTIAL'},
        'witness_ref': 'W_AND',
    })
    assertions = list(s.store.ledger.data['assertions'].values())
    assert len(assertions) == 3
    assert all(a['witness_ref'] == 'W_AND' for a in assertions)
    assert sum(a['provenance']['support']['kind'] == 'DERIVED' for a in assertions) == 2
    s.action('retract_observation', {'observation': 'O_and'})
    assert all(a['status'] == 'RETRACTED' for a in s.store.ledger.data['assertions'].values())
    assert not s.store.ledger.paths()


def test_late_incompatibility_rescan_preserves_both_facts(tmp_path):
    s = session(tmp_path)
    temporal_action(s, 'seed_without_incompatibility', {
        'formulas': [ATOM, OTHER], 'windows': [
            {'kind': 'INTERVAL', 'bounds': [0, 3], 'semantics': 'CONTINUOUS'},
            {'kind': 'INTERVAL', 'bounds': [0, 3], 'semantics': 'EXISTENTIAL'},
        ],
    })
    result = temporal_action(s, 'change_declared_resource', {'rule': 'LOCATIVE_EXCLUSIVE', 'version': 2})
    assert result['reports']['open_count'] == 1
    assert result['store']['fact_count'] == 2
    assert result['store']['auto_retraction_count'] == 0


def test_symbolic_constraints_and_declared_temporal_region():
    with pytest.raises(ValueError, match='CONSTRAINT_CONFLICT'):
        validate_order_constraints([['t1', 'BEFORE', 't2'], ['t2', 'BEFORE', 't1']])
    assert validate_order_constraints([['t1', 'BEFORE', 't2']]) == ('t1', 't2')
    rule = InferenceRule('fixture-rule', 'CUSTOM', 'DECLARED')
    with pytest.raises(ValueError, match='INFERENCE_TEMPORAL_MISMATCH'):
        derive_declared_region(rule, [cont(0, 3)] * 3, None)
    assert derive_declared_region(rule, [cont(0, 3)] * 3, point(1)) == point(1)


def test_cross_source_open_roots_never_get_equated(tmp_path):
    s = session(tmp_path)
    result = temporal_action(s, 'open_or_cross_source', {
        'or_operand_observation': 'O1', 'not_operand_observation': 'O2',
        'same_surface': 'глоркнул', 'same_roles': True, 'same_time': True,
        'declared_equivalence': False,
    })
    assert len(set(result['open']['identity_keys'])) == 2
    assert result['answer']['status'] == 'UNKNOWN'
    assert result['derived']['support_count'] == 0
    assert result['aliases'] == []
    assert len(s.store.ledger.data['supports']) == 2


def test_failed_goal_preflight_does_not_invent_durable_decision(tmp_path):
    s = session(tmp_path)
    temporal_action(s, 'seed_temporal_or', {
        'or_formula': OR, 'not_formula': NOT,
        'or_window': {'kind': 'POINT', 't': 5},
        'not_window': {'kind': 'POINT', 't': 6},
    })
    result = temporal_action(s, 'derive_or', {
        'root_witness': {'kind': 'POINT', 't': 5},
        'not_witness': {'kind': 'POINT', 't': 6},
    })
    assert result['license']['stage'] == 'PREFLIGHT'
    assert result['goal']['started'] is False
    assert 'outcome' not in result['goal']
    assert not any(record['payload'].get('kind', '').startswith('GOAL_')
                   for record in s.store._journal.scan_unprocessed(0))
