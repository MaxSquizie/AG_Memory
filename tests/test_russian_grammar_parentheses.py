from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def _stored_rows(text):
    core = AHCore()
    reply = submit(core, text)
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    return [core.store.get_element(Domain.H, member.uid).meta for member in group.members]


def test_numeric_explanation_and_distinct_main_count():
    rows = _stored_rows('Завод выпустил 30 машин (12%).')
    words = {row['surface']: row for row in rows}
    assert words['12']['quantity'] == '12'
    assert rows[words['12']['head']]['surface'] == '%'
    assert rows[words['%']['head']]['surface'] == 'машин'
    assert words['12']['assertion_status'] == 'parenthetical'
    assert words['30']['quantity'] == '30'
    assert words['выпустил']['assertion_status'] == 'asserted'


def test_parenthetical_actor_is_kept_local():
    rows = _stored_rows('Анна увидела брата (музыкант, играет на сцене).')
    words = {row['surface']: row for row in rows}
    assert rows[words['музыкант']['head']]['surface'] == 'брата'
    assert rows[words['играет']['controller']]['surface'] == 'музыкант'
    assert words['играет']['assertion_status'] == 'parenthetical'
    for sentence in ('Анна увидела брата (который).', 'Завод выпустил 30 машин (12%.'):
        core = AHCore()
        assert submit(core, sentence).status != 'STORED'
        assert not core.store.links()
