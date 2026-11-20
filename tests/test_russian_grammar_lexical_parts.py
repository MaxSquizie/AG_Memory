import pytest

from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.lexical_parts import metadata
from ah.russian_grammar.memory import submit
from ah.russian_grammar.rules import known_forms


@pytest.mark.parametrize(('text', 'term', 'lemma', 'parts'), [
    ('Методика АГ-памяти работает.', 'АГ-памяти', 'аг-память', ('АГ', 'памяти')),
    ('Модернизация ИТ‑системы завершилась.', 'ИТ‑системы', 'ит-система', ('ИТ', 'системы')),
    ('Вуз открыл лабораторию.', 'Вуз', 'вуз', ('Вуз',)),
    ('Иван работает в МИДе.', 'МИДе', 'мид', ('МИДе',)),
])
def test_term_keeps_identity_morphology_and_original_parts(text, term, lemma, parts):
    core = AHCore()
    result = submit(core, text)
    assert result.status == 'STORED'
    group = core.store.get_element(Domain.H, result.observation_ref)
    row = next(row for ref in group.members
               if (row := core.store.get_element(Domain.H, ref.uid).meta)['surface'] == term)
    assert row['lemma'] == lemma
    atoms = row['lexical_parts']
    assert tuple(text[part['start']:part['end']] for part in atoms) == parts
    if len(parts) > 1:
        assert row['morphology']['case'] == 'gent'
    assert atoms[0]['abbreviation_evidence'] == ('capitalization' if term == 'АГ-памяти' else 'dictionary')


def test_opaque_nominal_requires_confirmation_without_expansion_or_guessed_gender():
    text = 'МРТ работает.'
    core = AHCore()
    result = submit(core, text, lambda p: '?' if 'обозначение' in p.question else 'МРТ')
    assert result.status == 'AMBIGUOUS'
    assert not core.store.elements(Domain.H)
    result = submit(core, text, lambda p: 'МРТ')
    group = core.store.get_element(Domain.H, result.observation_ref)
    row = core.store.get_element(Domain.H, group.members[0].uid).meta
    assert row['lemma'] == 'МРТ'
    assert row['role'] == 'subject'
    assert row['morphology']['gender'] is None and row['morphology']['number'] is None
    assert row['lexical_parts'][0]['abbreviation_evidence'] == 'capitalization'
    assert {lemma for lemma, _ in known_forms('АГ-памяти')} == {'аг-память'}
    assert {lemma for lemma, _ in known_forms('УШЁЛ')} == {'уйти'}


def test_capitals_do_not_reclassify_attested_compounds_or_roman_numerals():
    assert metadata('ВАГОН-ресторан', 0, 'вагон-ресторан') == ()
    assert metadata('ВАГОНА-ресторана', 0, 'вагон-ресторан') == ()
    assert metadata('XIX-века', 0, 'xix-век') == ()
    assert metadata('УШЁЛ', 0, 'уйти') == ()
