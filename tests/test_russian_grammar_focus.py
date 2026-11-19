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
