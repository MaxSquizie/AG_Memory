from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def observation(core, reply):
    group = core.store.get_element(Domain.H, reply.observation_ref)
    return [core.store.get_element(Domain.H, member.uid).meta for member in group.members]


def test_detached_measure_and_qualification_have_distinct_hosts():
    core = AHCore()

    def resolve(probe):
        return 'мачта' if 'указание меры' in probe.question else 'метров'

    reply = submit(core, 'Здесь упала мачта, 12 метров в высоту.', resolve)
    assert reply.status == 'STORED'
    rows = observation(core, reply)
    assert rows[4]['quantity'] == '12'
    assert rows[5]['role'] == 'measure' and rows[5]['head'] == 2
    assert rows[6]['head'] == 5 and rows[7]['head'] == 6

    def age(probe):
        return next(word for word in ('по словам мэра', 'может', 'Мосту') if word in probe.options)

    reply = submit(core, 'Мосту, по словам мэра, может быть сто лет.', age)
    assert reply.status == 'STORED'
    rows = observation(core, reply)
    assert rows[0]['role'] == 'experiencer'
    assert rows[6]['assertion_status'] == 'qualified'


def test_nearest_subject_and_unlisted_attribute_need_independent_evidence():
    core = AHCore()
    assert submit(core, 'Пришла брат и сестра.').status == 'UNRESOLVED'
    assert submit(core, 'Здесь растёт Флюмбергская сосна.', lambda p: '?').status == 'AMBIGUOUS'
    assert not core.store.elements(Domain.H)
    rows = observation(core, submit(core, 'Нужна сетка и трос.'))
    assert rows[1]['role'] == 'subject' and rows[3]['head'] == 1
    rows = observation(core, submit(core, 'Здесь растёт Флюмбергская сосна.', lambda p: 'сосна'))
    assert rows[2]['role'] == 'attribute' and rows[2]['head'] == 3
