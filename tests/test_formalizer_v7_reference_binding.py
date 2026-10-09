"""Real reference/commit boundaries; fixture payloads contain no oracle checks."""
import pytest

from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_reference_binding import reference_action, reference_snapshot


def session(tmp_path, payloads=()):
    return Session(list(payloads), tmp_path / 'journal.log')


@pytest.mark.parametrize('distance,admitted', [(127, True), (128, True), (129, False)])
def test_coreference_window_uses_actual_token_positions(tmp_path, distance, admitted):
    p = {'declared_antecedent': 'ivan', 'distance_tokens': distance, 'max_window': 128,
         'text': 'Он пришёл.', 'value_ground': 'P:O1'}
    s = session(tmp_path)
    result = reference_action(s, 'resolve_reference_window', p)
    assert result['reference']['distance_tokens'] == distance
    assert result['reference']['candidate_in_window'] is admitted
    assert result['binding']['created'] is admitted


def test_reference_positive_grounds_do_not_become_facts(tmp_path):
    s = session(tmp_path)
    result = reference_action(s, 'resolve_reference', {
        'antecedents': ['ivan', 'petr'], 'text': 'Он вошёл.',
        'value_grounds': {'ivan': ['P:O1'], 'petr': ['P:O2']}})
    assert result['decision']['outcome'] == 'AMBIGUOUS'
    assert set(result['alternatives']['entities']) == {'ivan', 'petr'}
    assert not s.store.ledger.f_visible()
    assert not s.store.ledger.data['supports']


def test_versioned_reference_retraction_invalidates_binding_and_current_fact(tmp_path):
    p = {'raw_input': {'text': 'Он взлетел.', 'source_id': 'O_cur', 'revision': 1,
        'range': [0, 11], 'language': 'ru', 'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'},
        'context_version': 1, 'generation_antecedents': []}
    s = session(tmp_path)
    v1 = reference_action(s, 'formalize_reference_with_context', p)
    assert v1['decision']['outcome'] == 'UNRESOLVED'
    v2 = reference_action(s, 'declare_context_version', {'antecedent': 'plane',
        'antecedent_ground': 'P:O_plane', 'antecedent_observation': 'O_plane',
        'context_version': 2, 'morphology': {'plane': 'masc', 'runway': 'femn'},
        'observation': 'O_cur'})
    assert v2['decision']['outcome'] == 'RESOLVED'
    assert v2['binding']['target'] == 'plane'
    assert v2['supports']['root_ground_types'] == ['O']
    v3 = reference_action(s, 'declare_context_version', {'context_version': 3,
        'irrelevant_resource_change': True, 'observation': 'O_cur'})
    assert v3['identity']['interpretation_version'] == 3
    assert reference_snapshot(s)['facts']['current_visible']
    s.action('retract_observation', {'observation': 'O_plane'})
    current = reference_snapshot(s)
    assert current['binding']['status'] == 'INVALID'
    assert not current['facts']['current_visible']
    assert not current['observations']['O_cur']['retracted']


def test_completed_t4_mixed_state_builds_only_resolved_fragment(tmp_path):
    s = session(tmp_path)
    result = reference_action(s, 'completed_t4_state', {
        'outcomes': ['RESOLVED', 'UNRESOLVED'], 'resolved_fragment_count': 1})
    assert result['version']['state'] == 'RESOLVED'
    assert result['decisions']['machine_states'] == ['RESOLVED_LOCAL', 'PROVISIONAL']
    assert result['plan']['fragment_count'] == 1
    assert not s.store.ledger.f_visible()


def test_duplicate_candidate_identity_is_rejected_at_seal(tmp_path):
    result = reference_action(session(tmp_path), 'candidate_id_collision', {
        'forced_digest': 'collision', 'payloads': [{'surface': 'а'}, {'surface': 'б'}]})
    assert 'INTEGRITY_ERROR' in result['diagnostics']['codes']
    assert not result['runtime']['sealed']


def test_nearest_form_remains_a_hypothesis_without_automatic_replacement(tmp_path):
    result = reference_action(session(tmp_path), 'lexical_candidates', {
        'text': 'Ксавир приехал.', 'surface': 'Ксавир',
        'nearest_dictionary_form': 'Ксавье', 'typo_ground': None})
    assert 'Ксавир' in result['lexical']['retained_surfaces']
    assert result['lexical']['auto_replacements'] == []
    assert any('Ксавье' in h['variants'] for h in result['runtime']['token_hypotheses'])
