import pytest

from ah.core import AHCore
from ah.russian_grammar.memory import submit
from ah.russian_grammar.parser import analyze


def test_quantified_groups_preserve_attachment_and_answers():
    core = AHCore()
    text = 'Этот студент прочитал каждую книгу'
    reply = submit(core, text)
    assert reply.status == 'STORED'
    tree, = reply.analysis.analyses
    assert [(link.head, link.scope) for link in tree if link.rule == 'NP.DET'] == [
        (1, 'demonstrative'), (4, 'universal')]
    assert submit(core, text + '?').text == 'Да.'
    assert submit(core, 'Что прочитал этот студент?').text == 'каждую книгу'
    assert submit(core, 'Кто прочитал книгу?').status == 'UNKNOWN'
    assert submit(core, 'Каждый студент имеет учебник.').status == 'STORED'
    assert submit(core, 'Кто имеет учебник?').text == 'Каждый студент'
    assert submit(core, 'Что имеет студент?').status == 'UNKNOWN'
    tree, = analyze('Все эти студенты прочитали книгу').analyses
    assert [(link.head, link.scope) for link in tree[:2]] == [(2, 'universal'), (2, 'demonstrative')]


@pytest.mark.parametrize(('text', 'host', 'scope'), [
    ('Только Анна прочитала письмо', 1, 'focus_exclusive'),
    ('Анна только прочитала письмо', 2, 'exclusive'),
    ('Не Анна прочитала письмо', 1, 'focus_negated'),
    ('Анна не прочитала письмо', 2, 'negated'),
])
def test_focus_is_position_sensitive_in_memory(text, host, scope):
    core = AHCore()
    reply = submit(core, text)
    assert reply.status == 'STORED'
    tree, = reply.analysis.analyses
    assert tree[host].scope == scope
    assert next(link.head for link in tree if link.role == 'particle') == host
    assert submit(core, text + '?').text == 'Да.'
    assert submit(core, 'Анна прочитала письмо?').status == 'UNKNOWN'
    expected = 'Анна' if scope == 'focus_exclusive' else 'Неизвестно.'
    assert submit(core, 'Кто прочитал письмо?').text == expected


@pytest.mark.parametrize('text', [
    'Ни один студент не прочитал книгу', 'Анна не прочитала ни одной книги',
    'Никакой студент не прочитал книгу',
])
def test_negative_concord_requires_negation(text):
    core = AHCore()
    assert submit(core, text).status == 'STORED'
    assert submit(core, text + '?').text == 'Да.'
    assert submit(core, 'Кто прочитал книгу?').status == 'UNKNOWN'
    assert not analyze(text.replace(' не ', ' ')).analyses


def test_at_least_one_preserves_lower_bound():
    core = AHCore()
    reply = submit(core, 'Анна прочитала хотя бы одну книгу.')
    assert reply.status == 'STORED'
    assert submit(core, 'Что прочитала Анна?').text == 'хотя бы одну книгу'
    assert submit(core, 'Анна прочитала ровно одну книгу?').status == 'UNKNOWN'


@pytest.mark.parametrize('text', [
    'Только Ольга не прочитала письмо.',
    'Если только Ольга прочитала письмо, Иван ушёл.',
])
def test_restricted_exclusive_does_not_answer_unconditional_question(text):
    core = AHCore()
    assert submit(core, text).status == 'STORED'
    assert submit(core, 'Кто прочитал письмо?').status == 'UNKNOWN'


def test_overlapping_focus_and_preposition_choices():
    from ah.model import Domain
    from ah.russian_grammar.probe import Probe

    text = 'Уже в начале тридцатых годов автомобили стали делать обтекаемыми'
    for anchor in ('в начале', 'стали делать'):
        for event in ('стали', 'делать'):
            core = AHCore()

            def select(probe):
                if probe.focus_choices:
                    assert Probe.from_prompt(probe.prompt()).jev_request() == probe.jev_request()
                    assert probe.options == ('в начале', 'стали делать')
                    return anchor
                if 'нет такого сочетания' in probe.options:
                    assert 'в начале тридцатых годов' in probe.options
                    return 'нет такого сочетания'
                assert set(probe.options) == {'стали', 'делать'}
                return event

            reply = submit(core, text, select)
            assert reply.status == 'STORED'
            group = core.store.get_element(Domain.H, reply.observation_ref)
            refs = {core.store.get_element(Domain.H, ref.uid).meta['surface']: ref for ref in group.members}
            links = {(edge.source, edge.relation_id, edge.target) for edge in core.store.links()}
            assert (refs['в'], 'grammar.preposition', refs[event]) in links
            assert (refs['начале'], 'grammar.governed', refs['в']) in links
            assert (refs['годов'], 'grammar.genitive_modifier', refs['начале']) in links
            target, = (end for start, relation, end in links if start == refs['Уже'] and relation == 'grammar.modifier_scope')
            assert core.store.get_element(Domain.H, target.uid).members == tuple(refs[w] for w in anchor.split())


def test_focus_abstention_and_replayed_question(tmp_path):
    from ah.core.journal import JournalChannel
    from ah.model import Domain

    text = 'Ещё в школе Иван пел'
    for answer, status in [('?', 'AMBIGUOUS'), ('0', 'UNRESOLVED')]:
        empty = AHCore()
        assert submit(empty, text, lambda p: answer).status == status
        assert not empty.store.elements(Domain.H) and not empty.store.links()
    journal = JournalChannel(tmp_path / 'focus.log')
    assert submit(AHCore(), text, lambda p: 'в школе', journal=journal).status == 'STORED'
    reader = AHCore()
    assert submit(reader, text + '?', lambda p: 'в школе', journal=journal).text == 'Да.'
    assert submit(reader, text + '?', lambda p: 'пел', journal=journal).status == 'UNKNOWN'
    assert not analyze('Вчера в школе Иван пел').probes
