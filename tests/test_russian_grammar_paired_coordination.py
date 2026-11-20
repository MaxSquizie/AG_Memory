import pytest

from ah.core import AHCore
from ah.russian_grammar.memory import submit


@pytest.mark.parametrize(('statement', 'question', 'answer'), [
    ('Ни Иван, ни Мария не пришли.', 'Кто не пришёл?', 'Ни Иван, ни Мария'),
    ('Не только Иван но и Мария ушла.', 'Кто ушёл?', 'Не только Иван но и Мария'),
    ('Иван взял не только книгу, но и тетрадь.', 'Что взял Иван?', 'не только книгу, но и тетрадь'),
    ('Иван не только пел, но и плясал.', 'Кто плясал?', 'Иван'),
    ('Он не видел ни Ивана, ни Марию, ни Петра.', 'Кого он не видел?', 'ни Ивана, ни Марию, ни Петра'),
])
def test_scope_and_group_answer(statement, question, answer):
    core = AHCore()
    record = submit(core, statement)
    assert record.status == 'STORED' and not record.analysis.probes
    assert submit(core, question).text == answer
    if 'не пришли' in statement:
        assert submit(core, 'Кто пришёл?').status == 'UNKNOWN'


def test_alternative_with_li_does_not_assert_either_event():
    core = AHCore()
    record = submit(core, 'То ли шёл дождь, то ли падал снег.')
    assert record.status == 'STORED'
    tree, = record.analysis.analyses
    assert all(link.role == 'coordinator_part' for link in tree if link.lemma == 'ли')
    assert submit(core, 'Шёл дождь?').status == 'UNKNOWN'
    assert submit(core, 'Падал снег?').status == 'UNKNOWN'
