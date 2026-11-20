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


def test_unmarked_group_grows_on_prefix_and_requires_a_scope_choice():
    from ah.russian_grammar.parser import Occurrence
    from ah.russian_grammar.qualification import openings

    surfaces = 'Мосту по расчётам опытных инженеров может быть сто лет'.split()
    tokens = tuple(Occurrence(s, i, i + 1) for i, s in enumerate(surfaces))
    assert not tuple(openings(tokens[:2]))
    opening, = openings(tokens[:3])
    assert (opening.left, opening.start, opening.noun) == (0, 1, 2)

    text = ' '.join(surfaces) + '.'
    phrase = 'по расчётам опытных инженеров'
    for choice, status in [(phrase, 'qualified'), ('нет такого сочетания', 'asserted'),
                           ('?', 'AMBIGUOUS'), ('0', 'UNRESOLVED')]:
        core = AHCore()
        asked = []

        def select(probe):
            if probe.options == (phrase, 'нет такого сочетания'):
                asked.append(probe)
                return choice
            return 'может' if 'может' in probe.options else 'Мосту'

        reply = submit(core, text, select)
        assert len(asked) == 1
        if choice in {'?', '0'}:
            assert reply.status == status and not core.store.elements(Domain.H)
        else:
            assert reply.status == 'STORED'
            row = next(w for w in observation(core, reply) if w['surface'] == 'может')
            assert row['assertion_status'] == status
