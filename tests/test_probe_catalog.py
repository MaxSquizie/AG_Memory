"""Report names and wire outcomes never substitute for semantic validation."""
from copy import deepcopy
import hashlib
import json

import pytest

from ah.diagnostics.probe_catalog import (
    LABEL_PROTOCOL, catalog_snapshot, classify_reply, evidence_clipped, resolve_slot,
)


AUDIT = {'protocol': LABEL_PROTOCOL, 'slot': 'structural_relation',
         'candidates': ['LEXICAL', 'AND']}
PROMPT = ('Decision slot: structural_relation\nOptions:\n1. One event\n2. Both events\n'
          'Reply with the number of the supported option. Insufficient context: ?\n'
          'No candidate fits: 0\nOne line, no spaces.')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def test_snapshot_hashes_registry_and_reporting_aliases_separately(monkeypatch):
    from ah.diagnostics import probe_catalog
    from ah.formalizer.probe_families import FAMILIES

    snapshot = catalog_snapshot()
    assert set(snapshot['slots']) == set(FAMILIES)
    assert snapshot['schema_version'] == 'probe-catalog-1'
    assert snapshot['registry_sha256'] == digest({key: snapshot[key]
        for key in ('slots', 'source_collection')})
    assert snapshot['catalog_sha256'] == digest({key: value for key, value in snapshot.items()
                                               if key != 'catalog_sha256'})
    monkeypatch.setattr(probe_catalog, 'ALIASES', {**snapshot['aliases'], 'older_name': 'child_slot'})
    changed = catalog_snapshot()
    assert changed['registry_sha256'] == snapshot['registry_sha256']
    assert changed['catalog_sha256'] != snapshot['catalog_sha256']
    snapshot['slots']['child_slot']['required_data'].append('external mutation')
    assert 'external mutation' not in FAMILIES['child_slot'].required_data
    assert 'external mutation' not in catalog_snapshot()['slots']['child_slot']['required_data']


def test_alias_is_only_a_report_name_and_unregistered_slots_remain_unregistered():
    catalog = catalog_snapshot()
    old = resolve_slot('structural_oov_reading', catalog)
    assert old['raw_slot'] == 'structural_oov_reading'
    assert old['canonical_slot'] == 'structural_oov_function'
    assert old['alias_applied'] and old['alias_semantic_equivalence'] is False
    assert old['registry_status'] == 'REGISTERED'
    for slot in ('structural_quantifier_kind', 'structural_group_next',
                 'nominal_coordination_discovery', 'nominal_coordination_marking',
                 'structural_shared_material'):
        observed = resolve_slot(slot, catalog)
        assert observed['canonical_slot'] == slot
        assert observed['registry_status'] == 'UNREGISTERED_OBSERVED'
        assert observed['family'] is None
    boundary = 'structural_parent_end'
    assert resolve_slot(boundary, catalog)['registry_status'] == 'UNREGISTERED_OBSERVED'
    recorded = resolve_slot(boundary, catalog, catalog['source_collection'])
    assert recorded['registry_status'] == 'DYNAMIC_SOURCE_COLLECTION'
    assert recorded['family_evidence'] == 'RECORDED_CONTRACT'


@pytest.mark.parametrize(('raw', 'outcome', 'ids'), [
    (' \r\n?\t', 'INSUFFICIENT_CONTEXT', []), ('\n0\n', 'NONE_FIT', []),
    (' 1\n', 'CHOSEN_ONE', ['LEXICAL']), ('\n2,1\r\n', 'CHOSEN_MULTIPLE', ['AND', 'LEXICAL']),
])
def test_outer_whitespace_and_multiple_choices_match_closed_label_transport(raw, outcome, ids):
    original = deepcopy(AUDIT)
    result = classify_reply(raw, audit=AUDIT, prompt=PROMPT)
    assert result['outcome'] == outcome
    assert result['selected_ids'] == ids
    assert result['normalized_response'] == raw.strip()
    assert AUDIT == original


@pytest.mark.parametrize('raw', ['999', '0,1', '1,1', '01', '1, 2', '1\n2', '١', '',
                                 'Explanation: 1', '9' * 5000])
def test_invalid_grammar_duplicates_and_out_of_domain_are_not_selections(raw):
    assert classify_reply(raw, audit=AUDIT)['outcome'] == 'MALFORMED'


@pytest.mark.parametrize('audit', [
    {**AUDIT, 'candidates': ['LEXICAL', {'_omitted_items': 80}]},
    {**AUDIT, 'candidates': ['LEXICAL'], '_omitted_fields': 1},
    {**AUDIT, 'candidates_truncated': True},
    {**AUDIT, 'candidates': ['LEXICAL', 'LEXICAL']},
    {**AUDIT, 'candidates': {'_trace_unserializable': 'unsupported'}},
])
def test_clipped_or_invalid_candidate_audit_never_certifies_an_ordinal(audit):
    result = classify_reply('1', audit=audit, prompt=PROMPT)
    assert result['outcome'] == 'UNKNOWN_EVIDENCE'
    assert result['selected_ids'] is None
    assert result['mapping_complete'] is False


def test_displayed_labels_validate_ordinals_without_inventing_internal_ids():
    result = classify_reply('1,2', prompt=PROMPT)
    assert result['outcome'] == 'CHOSEN_MULTIPLE'
    assert result['selected_ids'] is None
    assert result['mapping_complete'] is False
    assert result['domain_evidence'] == 'COMPLETE_DISPLAYED_LABELS_ONLY'
    assert result['selected_display_labels'] == ['One event', 'Both events']
    assert classify_reply('3', prompt=PROMPT)['outcome'] == 'MALFORMED'
    assert classify_reply('1', prompt=PROMPT, prompt_complete=False)['outcome'] == 'UNKNOWN_EVIDENCE'


def test_historical_inline_ids_are_mapped_only_from_complete_evidence():
    prompt = PROMPT + '\nAudit mapping:\n1 = "LEXICAL"\n2 = "AND"'
    result = classify_reply('2,1', prompt=prompt)
    assert result['selected_ids'] == ['AND', 'LEXICAL']
    assert result['domain_evidence'] == 'COMPLETE_INLINE_ID_MAP'
    assert classify_reply('1', prompt=prompt, prompt_complete=False,
                          protocol=LABEL_PROTOCOL)['outcome'] == 'UNKNOWN_EVIDENCE'


def test_transport_errors_missing_responses_and_clipping_are_distinct_from_malformed():
    assert classify_reply(None, audit=AUDIT, response_present=False,
                          provider_error='HTTP 503')['outcome'] == 'PROVIDER_ERROR'
    assert classify_reply(None, audit=AUDIT, unfinished=True)['outcome'] == 'UNFINISHED'
    assert classify_reply(None, audit=AUDIT, response_present=False)['outcome'] == 'UNKNOWN_EVIDENCE'
    assert classify_reply('?', audit=AUDIT, response_truncated=True)['outcome'] == 'TRUNCATED'
    assert classify_reply('1', audit={**AUDIT, 'protocol': 'JSON_V1'})['outcome'] == 'UNKNOWN_EVIDENCE'
    assert classify_reply('?', prompt='Insufficient context: ?')['outcome'] == 'UNKNOWN_EVIDENCE'
    result = classify_reply({'_trace_unserializable': 'unsupported'}, audit=AUDIT)
    assert result['outcome'] == 'UNKNOWN_EVIDENCE' and result['response_complete'] is False
    assert evidence_clipped({'nested': [{'x': {'_trace_unserializable': 'cycle'}}]})
    assert not evidence_clipped({'candidates': ['ordinary value'], '_omitted_items': 0})
