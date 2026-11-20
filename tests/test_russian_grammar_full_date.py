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
