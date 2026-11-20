from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_calendar_date_attaches_to_event_and_checks_leap_year():
    core = AHCore()
    result = submit(core, '29 февраля 2024 года Анна открыла окно.')
    assert result.status == 'STORED'
    observation = core.store.get_element(Domain.H, result.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in observation.members]
    assert rows[rows[0]['head']]['surface'] == 'открыла'
    assert [row['surface'] for row in rows[:4]] == ['29', 'февраля', '2024', 'года']
    empty = AHCore()
    assert submit(empty, '29 февраля 2023 года Анна открыла окно.').status == 'UNRESOLVED'
    assert not empty.store.elements(Domain.H)


def test_calendar_ordinal_and_population_have_distinct_numeric_roles():
    core = AHCore()
    assert submit(core, 'В 2018 году было 235 человек').status == 'STORED'
    assert submit(core, 'Сколько человек было в 2018 году?').text == '235'
    assert submit(core, 'В 2017 году было 235 человек?').status == 'UNKNOWN'
    reply = submit(core, 'Иван ушёл в 1 году', lambda probe: '?')
    assert reply.status == 'AMBIGUOUS'
    assert {tree[3].quantity_kind for tree in reply.analysis.analyses} == {'ordinal', 'cardinal'}
