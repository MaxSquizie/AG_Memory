import pytest

from ah.core.operations import AHCore
from ah.russian_grammar.memory import submit
from ah.russian_grammar.parser import analyze


def test_gap_has_two_events_and_preserves_real_offsets():
    core = AHCore()
    sentence = 'Анна купила книгу, а Иван — журнал.'
    stored = submit(core, sentence)
    assert stored.status == 'STORED'
    tree, = stored.analysis.analyses
    gap = next(i for i, link in enumerate(tree) if link.rule == 'GAP')
    token = stored.analysis.tokens[gap]
    assert sentence[token.start:token.end] == '—'
    assert tree[gap].lemma == tree[tree[gap].head].lemma == 'купить'
    assert [(v.role, v.lemma) for v in tree if v.head == gap and v.rule.startswith('GAP.')] == [
        ('subject', 'иван'), ('object', 'журнал')]
    assert submit(core, 'Что купил Иван?').text == 'журнал'
    assert submit(core, 'Что купила Анна?').text == 'книгу'


@pytest.mark.parametrize('sentence', [
    'Анна купила книгу, или Иван — журнал.',
    'Если Анна купила книгу, а Иван — журнал, Мария ушла.',
])
def test_scoped_gapping_does_not_assert_a_purchase(sentence):
    core = AHCore()
    assert submit(core, sentence).status == 'STORED'
    assert submit(core, 'Что купил Иван?').status == 'UNKNOWN'
    assert submit(core, 'Что купила Анна?').status == 'UNKNOWN'


def test_one_member_clauses():
    nominal, = analyze('Ночь.').analyses
    assert (nominal[0].lemma, nominal[0].case, nominal[0].rule) == ('ночь', 'nomn', 'NOM.EXIST')
    existential, = analyze('У меня нет книги.').analyses
    assert existential[2].scope == 'negated'
    assert (existential[1].lemma, existential[1].head, existential[3].case) == ('я', 0, 'gent')


def test_questions_preserve_groups_in_an_absence_claim():
    core = AHCore()
    assert submit(core, 'У маленькой девочки нет новой книги.').status == 'STORED'
    assert submit(core, 'У кого нет новой книги?').text == 'маленькой девочки'
    assert submit(core, 'Чего нет у маленькой девочки?').text == 'новой книги'
    assert submit(core, 'У кого нет книги?').status == 'UNKNOWN'
    assert submit(core, 'У маленькой девочки есть новая книга?').status in ('UNKNOWN', 'AMBIGUOUS')


def test_gapped_clause_with_extended_arguments():
    core = AHCore()
    assert submit(core, 'Анна купила новую книгу, а Иван — старый журнал.').status == 'STORED'
    assert submit(core, 'Что купил Иван?').text == 'старый журнал'
    assert submit(core, 'Что купила Анна?').text == 'новую книгу'
