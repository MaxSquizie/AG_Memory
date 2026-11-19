import pytest

from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import CONJUNCT_KEY, submit
from ah.russian_grammar.parser import analyze


def choose_shared_object(probe):
    return next((option for option in probe.options if ' и ' in option), probe.options[0])


def test_coordinated_nominals_and_attributes():
    core = AHCore()
    assert submit(core, 'Саша и Маша ушли.').status == 'STORED'
    assert submit(core, 'Кто ушёл?').text == 'Саша и Маша'
    for source in ('Старая и новая книги лежат на столе.', 'Старые и новые книги лежат на столе.'):
        tree, = (tree for tree in analyze(source).analyses if tree[0].role == 'attribute')
        assert [tree[i].head for i in (0, 2, 3)] == [3, 3, 4]
        assert [tree[i].role for i in (0, 1, 2)] == ['attribute', 'coordinator', 'attribute']


def test_future_and_modal_groups_keep_their_governor():
    readings = analyze('Иван будет читать и писать.').analyses
    assert readings and all(tree[4].controller == 0 and tree[4].morphology.tense == 'futr' for tree in readings)
    core = AHCore()
    assert submit(core, 'Иван будет читать и рисовать.').status == 'STORED'
    assert submit(core, 'Кто будет рисовать?').text == 'Иван'
    result = submit(core, 'Иван должен прочитать и подписать письмо.', choose_shared_object)
    assert result.status == 'STORED'
    group = core.store.get_element(Domain.H, result.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert rows[2]['controller'] == rows[4]['controller'] == 0
    assert rows[2]['shared_object'] == 5
    assert submit(core, 'Что Иван должен прочитать?').text == 'письмо'
    assert rows[2]['assertion_status'] == rows[4]['assertion_status'] == 'modal'
    assert submit(core, 'Кто подписал письмо?').status == 'UNKNOWN'
    assert submit(core, 'Иван ел и пил воду.', lambda _: '?').status == 'AMBIGUOUS'
    assert submit(core, 'Что Иван ел?').status == 'UNKNOWN'


@pytest.mark.parametrize(('source', 'checks'), [
    ('Иван открыл и закрыл окно.', [('Кто закрыл окно?', 'Иван'), ('Что Иван открыл?', 'окно')]),
    ('Иван открыл дверь и закрыл окно.', [('Кто закрыл окно?', 'Иван'), ('Кто открыл окно?', 'Неизвестно.')]),
    ('Иван открыл окно и Маша закрыла дверь.', [('Кто закрыл дверь?', 'Маша'), ('Кто открыл дверь?', 'Неизвестно.')]),
    ('Иван открыл или закрыл окно.', [('Кто закрыл окно?', 'Неизвестно.')]),
    ('Если Иван открыл и закрыл окно, Маша ушла.', [('Кто закрыл окно?', 'Неизвестно.')]),
])
def test_predicate_projection_respects_predicate_arguments_and_scope(source, checks):
    core = AHCore()
    assert submit(core, source, choose_shared_object).status == 'STORED'
    for question, answer in checks:
        assert submit(core, question).text == answer
    if source.startswith('Если') or ' или ' in source:
        assert not tuple(core.store.find_elements_with_property(CONJUNCT_KEY, 'закрыть'))


def test_alternative_infinitives_stay_inside_the_modal():
    core = AHCore()
    assert submit(core, 'Иван должен прочитать или подписать письмо.').status == 'STORED'
    assert submit(core, 'Кто должен подписать письмо?').status == 'UNKNOWN'
    assert submit(core, 'Кто должен прочитать?').status == 'UNKNOWN'
    assert submit(core, 'Кто подписал письмо?').status == 'UNKNOWN'


def test_indexed_conjunct_and_shared_object_survive_replay(tmp_path):
    from ah.core.journal import JournalChannel

    journal = JournalChannel(tmp_path / 'coordination.log')
    writer = AHCore()
    assert submit(writer, 'Иван открыл и закрыл окно.', choose_shared_object, journal=journal).status == 'STORED'
    assert submit(writer, 'Иван не ушёл, а Мария осталась.', journal=journal).status == 'STORED'
    reader = AHCore()
    for question, answer in [('Кто закрыл окно?', 'Иван'), ('Что Иван открыл?', 'окно'),
                             ('Кто остался?', 'Мария'), ('Кто ушёл?', 'Неизвестно.')]:
        assert submit(reader, question, journal=journal).text == answer


def test_embedded_conjunction_has_no_independent_index():
    core = AHCore()
    reply = submit(core, 'Маша сказала, что Иван открыл и закрыл окно.', lambda probe: probe.options[0])
    assert reply.status == 'STORED'
    tree, = reply.analysis.analyses
    assert tree[5].role == 'clause_complement' and tree[7].head == 5
    assert not tuple(core.store.find_elements_with_property(CONJUNCT_KEY, 'закрыть'))
    assert submit(core, 'Кто закрыл окно?').status == 'UNKNOWN'
