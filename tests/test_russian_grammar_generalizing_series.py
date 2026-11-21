import pytest

from ah.core import AHCore
from ah.russian_grammar.memory import submit


@pytest.mark.parametrize(('source', 'question', 'answer'), [
    ('На столе лежало всё: книги, письма и газеты.', 'Что лежало на столе?', 'книги, письма и газеты'),
    ('На столе лежало всё книги, письма и газеты.', 'Что лежало на столе?', 'книги, письма и газеты'),
    ('Книги, письма и газеты — всё лежало на столе.', 'Что лежало на столе?', 'Книги, письма и газеты'),
    ('Она купила продукты: хлеб и молоко.', 'Что она купила?', 'хлеб и молоко'),
    ('Она помогла всем: детям и сёстрам.', 'Кому она помогла?', 'детям и сёстрам'),
    ('Всё: книги, письма и газеты — лежало на столе.', 'Что лежало на столе?', 'книги, письма и газеты'),
])
def test_generalizing_head_and_list(source, question, answer):
    memory = AHCore()
    stored = submit(memory, source)
    assert stored.status == 'STORED'
    tree, = stored.analysis.analyses
    first, = (j for j, link in enumerate(tree) if link.rule == 'NP.ENUM')
    assert tree[tree[first].head].rule == 'NP.GENERALIZER'
    assert all(link.head == first and link.case == tree[first].case for link in tree if link.role == 'nominal_conjunct')
    assert submit(memory, question).text == answer


def test_list_evidence_and_unconfirmed_boundaries():
    core = AHCore()
    assert submit(core, 'На столе лежало всё книги письма и газеты.').status == 'AMBIGUOUS'
    assert submit(core, 'На столе лежало всё: книгам, письмам и газетам.').status == 'UNRESOLVED'
    assert submit(core, 'На столе лежало всё: книги, письма и газеты.').status == 'STORED'
    for item in ('Книги', 'Письма', 'Газеты'):
        assert submit(core, f'{item} лежали на столе?').status == 'EVIDENCE'
    assert submit(core, 'Кто лежал на столе?').status == 'UNKNOWN'
    regular = submit(core, 'Она купила все книги и тетради.')
    assert regular.status == 'STORED' and regular.analysis.analyses[0][2].role == 'attribute'


def test_postposed_generalizer_competes_with_gapping():
    core = AHCore()
    result = submit(core, 'Она купила хлеб и молоко — продукты.')
    assert result.status == 'AMBIGUOUS'
    assert set(result.analysis.probes[0].options) == {'продукты', 'купила'}
    assert submit(core, 'Что она купила?').status == 'UNKNOWN'
    assert submit(core, 'Иван купил книгу, а Мария — тетрадь.').status == 'STORED'
