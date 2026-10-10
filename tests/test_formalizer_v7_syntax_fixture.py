"""Generic declarative fixture grammar: exact coverage before any TP skip."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

import pytest

from ah.core.operations import AHCore
from ah.core.store import AHStore
from ah.formalizer.native_frontend import _grammar_frames
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.pipeline import MorphProvider, t0, t1
from ah.formalizer.state import MorphVariant
from ah.formalizer.syntax_rules import run_srl
from tools.formalizer_v7_syntax_fixture import finite_clause_rules
from tools.formalizer_v7_test_support import role, sign_test_release, test_release


def released(senses, *, max_arguments=3):
    core = AHCore(AHStore())
    base = test_release(core, senses)
    manifest = deepcopy(base.manifest)
    resources = {resource['kind']: resource for resource in manifest['entries']}
    resources['SyntaxRules']['entries'] = finite_clause_rules(
        {kind: resource['entries'] for kind, resource in resources.items()},
        max_arguments=max_arguments)
    resources['SyntaxRules']['dependency_versions'] = {
        kind: resources[kind]['version'] for kind in ('R-S', 'R-V')}
    manifest['coverage_report']['resource_content_sha256'] = digest({
        kind: manifest[kind] for kind in ('kind', 'version', 'schema_version',
                                         'entries', 'dependency_versions')})
    manifest['coverage_report']['units_by_kind'] = {
        kind: len(resource['entries']) for kind, resource in resources.items()}
    release, _ = sign_test_release(manifest)
    release.validate_store(core.store)
    return release


def grammar(text, release, morph):
    state = t0(text)
    state.observation = {'observation_id': 'syntax-fixture', 'interpretation_version': 1}
    run_srl(state, release, morph)
    t1(state, morph=morph, preserve_variants=True, shared_form_expansion=False)
    state.frames = _grammar_frames(state, release)
    return state


@pytest.fixture(scope='module')
def morph():
    return MorphProvider()


@pytest.mark.parametrize('text', ['Курьер перенёс книгу.', 'Книгу перенёс курьер.',
                                'Перенёс курьер книгу!', 'Курьер книгу перенёс?'])
def test_known_transitive_clause_covers_all_words_independent_of_word_order(text, morph):
    release = released([('MOVE', 'перенести', 'VERB', [role('SUBJECT'), role('OBJECT', ('acc',))])])
    state = grammar(text, release, morph)
    assert len(state.frames) == 1
    frame = state.frames[0]
    tokens = {token.token_id: token.span.casefold() for token in state.evidence}
    assert {tokens[token]: bound for token, bound in frame.semantic['proposed_roles'].items()} == {
        'курьер': 'SUBJECT', 'книгу': 'OBJECT'}
    assert not frame.semantic['structural_unresolved']
    assert all(token.token_id in frame.semantic['morph_bindings']
               for token in state.evidence if token.span not in {'.', '!', '?'})


@pytest.mark.parametrize('text', [
    'Робот перенёс предмет быстро.',
    'Робот перенёс красный предмет.',
    'Робот перенёс предмет вчера.',
    'Робот не перенёс предмет.',
    'Робот перенёс предмет и ушёл.',
    'Робот перенёс предмет,',
    'Робот перенёс предмет на стол.',
    'Робот перенёс предмет квазитокен.',
    'Робот сказал: «Робот перенёс предмет».',
    'Робот перенести предмет.',
    'Робот перенёс.',
])
def test_uncaptured_content_and_nonfinite_scope_never_look_complete(text, morph):
    release = released([('MOVE', 'перенести', 'VERB', [role('SUBJECT'), role('OBJECT', ('acc',))])])
    assert grammar(text, release, morph).frames == []


def test_whole_morphological_alternatives_and_role_ties_remain_candidates():
    release = released([('OBSERVE', 'наблюдать', 'VERB',
                         [role('SUBJECT'), role('OBJECT', ('nom',))])])
    class AmbiguousMorph:
        def analyze(self, word):
            if word == 'наблюдает':
                return (MorphVariant(lemma='наблюдать', pos='VERB', score=1),)
            if word in {'А', 'Б'}:
                return (MorphVariant(lemma=word, pos='NOUN', cases=frozenset({'nom'}),
                                     number='sing', score=.99),
                        MorphVariant(lemma=word, pos='NOUN', cases=frozenset({'nom'}),
                                     number='plur', score=.01))
            return (MorphVariant(lemma=word, pos='PNCT'),)
    state = grammar('А наблюдает Б.', release, AmbiguousMorph())
    assert len(state.frames) == 8  # two role assignments × both whole parses per entity
    assert all(frame.semantic['structural_unresolved'] for frame in state.frames)
    signatures = Counter(tuple(sorted(frame.semantic['proposed_roles'].items())) for frame in state.frames)
    assert sorted(signatures.values()) == [4, 4]
    for token in state.evidence:
        if token.span in {'А', 'Б'}:
            assert {variant.score for variant in token.variants} == {.99, .01}


def test_released_valency_licence_does_not_leak_to_another_known_predicate(morph):
    release = released([
        ('MOVE', 'перенести', 'VERB', [role('SUBJECT'), role('OBJECT', ('acc',))]),
        ('WORK', 'работать', 'VERB', [role('SUBJECT')]),
    ])
    assert grammar('Робот работает.', release, morph).frames
    assert grammar('Робот работает предмет.', release, morph).frames == []
    assert grammar('Робот перенёс.', release, morph).frames == []


def test_optional_roles_enumerate_retained_subsets_not_new_valencies(morph):
    location = role('LOCATION', ('loc',))
    location.update(cardinality={'min': 0, 'max': 1}, optionality=True)
    release = released([('REST', 'сидеть', 'VERB', [role('SUBJECT'), location])])
    assert len(release.entries('SyntaxRules')) == 2
    assert len(grammar('Робот сидит.', release, morph).frames) == 1
    # The preposition itself is not captured by this grammar. A complete PP
    # needs a separately reviewed structural declaration, not a head shortcut.
    assert grammar('Робот сидит на стуле.', release, morph).frames == []


def test_non_entity_and_multiword_predicate_valencies_cannot_be_flattened(morph):
    content = role('OBJECT', ('acc',)); content['argument_types'] = ['PROPOSITION']
    release = released([('REPORT', 'сказать', 'VERB', [role('SUBJECT'), content])])
    assert release.entries('SyntaxRules') == []
    assert grammar('Робот сказал.', release, morph).frames == []
    resources = {'R-S': [{'sense_id': 'PHRASE', 'POS': 'VERB', 'lemma': 'нести',
                         'anchor_pattern': [{'lemma': 'нести'}, {'lemma': 'ответственность'}]}],
                 'R-V': [{'sense_id': 'PHRASE', 'roles': [role('SUBJECT')]}],
                 'RoleRegistry': [{'role_id': 'SUBJECT'}]}
    assert finite_clause_rules(resources) == []


def test_builder_is_pure_and_only_depends_on_released_data():
    resources = {'R-S': [{'sense_id': 'FINITE', 'POS': 'VERB', 'lemma': 'любая_лемма'}],
                 'R-V': [{'sense_id': 'FINITE', 'roles': [role('SUBJECT')]}],
                 'RoleRegistry': [{'role_id': 'SUBJECT'}]}
    before = deepcopy(resources)
    rules = finite_clause_rules(resources)
    assert resources == before
    assert rules == finite_clause_rules(resources)
    assert 'lemma' not in rules[0]['input_feature_pattern']['captures']['p']
    assert rules[0]['constraints'] == []  # no order-based pruning or ranking winner
    rules[0]['output']['nodes'].clear()
    assert finite_clause_rules(resources)[0]['output']['nodes']
    with pytest.raises(ValueError):
        finite_clause_rules(resources, max_arguments=4)
