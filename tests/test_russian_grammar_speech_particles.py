import pytest

from ah.core import AHCore
from ah.russian_grammar.memory import submit


@pytest.mark.parametrize('sentence', ['Иван спросил, придёт ли Анна.', 'Иван спросил придёт ли Анна'])
def test_embedded_question_is_content(sentence):
    core = AHCore()
    record = submit(core, sentence)
    assert record.status == 'STORED' and not record.analysis.probes
    assert submit(core, 'Что спросил Иван?').text == 'придёт ли Анна'
    assert submit(core, 'Придёт ли Анна?').status == 'UNKNOWN'
    assert submit(core, 'Анна придёт.').status == 'STORED'
    assert submit(core, 'Придёт ли Анна?').text == 'Да.'


@pytest.mark.parametrize('sentence,scope', [
    ('Иван едва ли пришёл.', 'doubt'), ('Вряд ли Иван пришёл.', 'doubt'),
    ('Иван едва ли не упал.', 'approximate'),
])
def test_particle_meaning_survives_commit(sentence, scope):
    core = AHCore()
    record = submit(core, sentence)
    assert record.status == 'STORED' and not record.analysis.probes
    tree, = record.analysis.analyses
    assert next(link for link in tree if link.head is None).scope == scope
    assert next(link for link in tree if link.lemma == 'ли').role == 'fixed'
    assert submit(core, 'Иван упал?' if scope == 'approximate' else 'Иван пришёл?').status == 'UNKNOWN'


def test_directive_and_concession():
    core = AHCore()
    assert submit(core, 'Пусть Иван войдёт.').status == 'DIRECTIVE'
    assert submit(core, 'Иван войдёт?').status == 'UNKNOWN'
    competition = submit(core, 'Пусть Иван придёт, но мы уйдём.')
    assert competition.status == 'AMBIGUOUS'
    assert competition.observation_ref is None


def test_misplaced_comma_is_an_explicit_choice():
    core = AHCore()
    for source in ('Едва, ли Иван придёт.', 'Иван спросил, придёт, ли Анна.', 'Пусть, Иван войдёт.'):
        result = submit(core, source)
        assert result.status == 'AMBIGUOUS' and result.observation_ref is None
        assert result.analysis.probes[-1].options[-1] == 'сохранить все запятые'
