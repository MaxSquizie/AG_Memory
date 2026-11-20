import pytest

from ah.core import AHCore
from ah.russian_grammar.memory import submit


def test_concession_is_factual_in_its_assertion_domain():
    for sentence in ('Хотя шёл дождь, Иван вышел.', 'Хотя шёл дождь Иван вышел'):
        core = AHCore()
        assert submit(core, sentence).status == 'STORED'
        assert submit(core, 'Иван вышел?').text == 'Да.'
        assert submit(core, 'Шёл дождь?').text == 'Да.'
    for sentence in ('Даже если шёл дождь, Иван вышел.', 'Мария сказала: «Хотя шёл дождь, Иван вышел».'):
        core = AHCore()
        assert submit(core, sentence).status == 'STORED'
        assert submit(core, 'Иван вышел?').status == 'UNKNOWN'
        assert submit(core, 'Шёл дождь?').status == 'UNKNOWN'


@pytest.mark.parametrize('sentence,question,answer', [
    ('Иван пришёл тогда, когда Мария ушла.', 'Когда пришёл Иван?', 'тогда, когда Мария ушла'),
    ('Иван работал столько сколько мог', 'Сколько работал Иван?', 'столько сколько мог'),
    ('Иван получил столько книг, сколько купил Пётр.', 'Сколько книг получил Иван?', 'столько книг, сколько купил Пётр'),
    ('Иван так замёрз, что задрожал.', 'Насколько замёрз Иван?', 'так, что задрожал'),
])
def test_the_whole_correlative_answers_the_matrix_question(sentence, question, answer):
    core = AHCore()
    record = submit(core, sentence)
    assert record.status == 'STORED'
    tree, = record.analysis.analyses
    marker, = (link for link in tree if link.rule == 'CL.CORRELATE')
    assert marker.head != marker.antecedent and marker.antecedent is not None
    assert submit(core, question).text == answer


def test_proportional_construction_links_the_two_comparative_scales():
    record = submit(AHCore(), 'Чем дольше Иван ждал, тем сильнее он волновался.')
    assert record.status == 'STORED'
    tree, = record.analysis.analyses
    first, second = (item for item in tree if item.rule == 'CL.SCALE')
    assert tree[first.antecedent] == second
    assert tree[first.head].lemma == 'долгий' and tree[second.head].lemma == 'сильный'
    assert tree[tree[first.head].head].scope == tree[tree[second.head].head].scope == 'proportional'
