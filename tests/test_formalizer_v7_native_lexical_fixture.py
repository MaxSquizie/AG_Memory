"""Oracle lexical fixtures declare POS variants; they do not alter runtime matching."""
import json
from unittest.mock import patch

import pytest

from ah.formalizer.pipeline import MorphProvider, t0
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import execute_native, fixture


def test_every_declared_finite_verb_has_explicit_infinitive_resources(tmp_path):
    session = Session([], tmp_path / 'lexical.log')
    release, aliases = fixture(session.core, 'known')
    morphology = MorphProvider()
    senses = release.entries('R-S')
    by_id = {sense['sense_id']: sense for sense in senses}
    for finite in senses:
        if finite['POS'] != 'VERB':
            continue
        # Pymorphy's actual POS distinction is retained, not expanded in code.
        assert any(v.pos == 'INFN' and v.lemma == finite['lemma']
                   for v in morphology.analyze(finite['lemma']))
        infinitive = by_id[finite['sense_id'] + '_INFN']
        assert infinitive['POS'] == 'INFN'
        assert infinitive['lemma'] == finite['lemma']
        finite_valencies = [v for v in release.entries('R-V')
                            if v['sense_id'] == finite['sense_id']]
        infinitive_valencies = [v for v in release.entries('R-V')
                                if v['sense_id'] == infinitive['sense_id']]
        assert finite_valencies and infinitive_valencies
        assert [v['roles'] for v in finite_valencies] == [v['roles'] for v in infinitive_valencies]
        finite_mappings = [m for m in release.entries('TemplateMap')
                           if m['sense_id'] == finite['sense_id']]
        infinitive_mappings = [m for m in release.entries('TemplateMap')
                               if m['sense_id'] == infinitive['sense_id']]
        assert {(m['template_ref'], tuple(m['roles'])) for m in finite_mappings} == {
            (m['template_ref'], tuple(m['roles'])) for m in infinitive_mappings}
        for mapping in infinitive_mappings:
            assert session.core.store.get_template(mapping['template_ref'])
            assert mapping['template_ref'] in aliases
    release.validate_store(session.core.store)


def test_broken_mapping_profile_stays_broken_for_both_verb_forms(tmp_path):
    session = Session([], tmp_path / 'broken.log')
    release, _ = fixture(session.core, 'known_mapping_broken')
    send = [s for s in release.entries('R-S') if s['lemma'] == 'отправить']
    assert {(s['POS'], s['sense_id']) for s in send} == {
        ('VERB', 'K_SEND'), ('INFN', 'K_SEND_INFN')}
    assert {v['sense_id'] for v in release.entries('R-V') if v['sense_id'].startswith('K_SEND')} == {
        'K_SEND', 'K_SEND_INFN'}
    assert not any(m['sense_id'] in {'K_SEND', 'K_SEND_INFN'}
                   for m in release.entries('TemplateMap'))


def test_sitting_transition_is_not_an_alias_of_sitting_state(tmp_path):
    session = Session([], tmp_path / 'sitting.log')
    release, aliases = fixture(session.core, 'known')
    finite = {s['lemma']: s for s in release.entries('R-S') if s['POS'] == 'VERB'}
    assert finite['сесть']['sense_id'] == 'SIT'
    assert finite['сидеть']['sense_id'] == 'SIT_STATE'
    transition = session.core.store.get_template('fixture:T:SIT')
    state = session.core.store.get_template('fixture:T:SIT_STATE')
    assert transition.uid != state.uid and transition.predicate != state.predicate
    assert aliases[transition.uid] == ('SIT', {'SUBJECT': 'AGENT'})
    assert aliases[state.uid] == ('SIT_STATE', {'SUBJECT': 'THEME', 'LOCATION': 'LOCATION'})
    valency = next(v for v in release.entries('R-V') if v['sense_id'] == 'SIT')
    assert valency['state_class'] == 'EVENT'
    assert valency['temporal_mode_hint'] == 'TRANSITION'
    assert not any(m['sense_id'] == 'SIT' and m['template_ref'] == state.uid
                   for m in release.entries('TemplateMap'))


def test_native_smoking_predicate_uses_its_real_fixture_template(tmp_path):
    class Backend:
        def generate(self, prompt, **_kwargs):
            data = json.loads(prompt)
            tokens = {t['text']: t['id'] for t in data['tokens']}
            return json.dumps({'hypotheses': [{'local_id': 'smoking-structure',
                'nodes': [{'kind': 'PREDICATE', 'anchor_spans': [tokens['курит']]},
                          {'kind': 'ENTITY', 'anchor_spans': [tokens['Иван']]}],
                'edges': [{'kind': 'ARGUMENT', 'from': 0, 'to': 1, 'role_id': 'SUBJECT'}],
                'alignment': [tokens['Иван'], tokens['курит']]}]})

    text = 'Иван курит.'
    payload = {'raw_input': {'text': text, 'source_id': 'lexical-fixture-smoke',
        'revision': 1, 'range': [0, len(text)], 'language': 'ru',
        'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    session = Session([payload], tmp_path / 'smoke.log')
    with patch('tools.formalizer_v7_native_binding.ChatBackend', return_value=Backend()):
        actual = execute_native(session, payload, {'provider': 'lmstudio', 'model': 'fixture'})
    assert actual['assertions']['ah'] == [
        {'predicate': 'SMOKE', 'roles': {'AGENT': {'entity': 'ivan'}}}]
    assert actual['runtime']['report']['terminal'] == 'APPLIED'
    mappings = [m for m in session.release.entries('TemplateMap') if m['sense_id'] == 'SMOKE']
    assert len(mappings) == 1
    assert mappings[0]['template_ref'] == 'fixture:T:SMOKE'
    assert session.core.store.get_template(mappings[0]['template_ref'])


@pytest.mark.parametrize('surface', ['мог', 'могла', 'могло', 'могли'])
def test_past_modal_forms_declare_required_possible_operator(tmp_path, surface):
    from ah.formalizer.native_frontend import _required_operators
    from ah.formalizer.selection_protocol import ProtocolError
    from ah.formalizer.tp_proposer import StructureProposalRequest, parse_and_validate

    session = Session([], tmp_path / 'modal.log')
    release, _ = fixture(session.core, 'known')
    state = t0(surface)
    required = _required_operators(state, release)
    token = state.evidence[0].token_id
    assert required == (('POSSIBLE', (token,)),)
    req = StructureProposalRequest('modal-fixture', 'pre-seal', (token,),
        allowed_node_kinds=frozenset({'PREDICATE', 'POSSIBLE'}),
        required_operators=required)
    without_modal_scope = {'hypotheses': [{'local_id': 'flattened-modal',
        'nodes': [{'kind': 'PREDICATE', 'anchor_spans': [token]}],
        'edges': [], 'alignment': [token]}]}
    with pytest.raises(ProtocolError):
        parse_and_validate(req, json.dumps(without_modal_scope))
