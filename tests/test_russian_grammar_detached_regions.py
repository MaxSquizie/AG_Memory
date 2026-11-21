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


def test_shared_comma_support_requires_identical_lexical_links():
    from dataclasses import replace
    from ah.russian_grammar.detached_prepositions import shared_comma_boundary
    from ah.russian_grammar.parser import Link

    first = (Link('predicate', 'жить', None, 'V1'),
             Link('preposition', 'в', 0, 'PP.DETACHED'), Link('governed', 'дом', 1, 'P1', 'loct'),
             Link('punctuation', ',', 2, 'PP.DETACHED.COMMA'),
             Link('preposition', 'с', 0, 'P2'), Link('governed', 'семья', 4, 'P1', 'ablt'))
    second = (first[0], replace(first[1], rule='P2'), first[2], replace(first[3], head=5),
              replace(first[4], rule='PP.DETACHED'), first[5])
    shared = shared_comma_boundary((first, second))
    assert shared == shared_comma_boundary((second, first))
    assert shared[3] == Link('punctuation', ',', 0, 'PUNCT.SHARED_BOUNDARY')
    assert shared[1:3] == second[1:3] and shared[4:] == first[4:]
    for index, changes in ((4, {'scope': 'qualification'}), (4, {'head': 2}), (2, {'rule': 'OPAQUE.GOVERNED'})):
        altered = list(second)
        altered[index] = replace(altered[index], **changes)
        assert shared_comma_boundary((first, tuple(altered))) is None
